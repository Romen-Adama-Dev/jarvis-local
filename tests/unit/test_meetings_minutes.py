import datetime
import json

import pytest

from packages.inference.base import InferenceResult
from packages.meetings.minutes import (
    Action,
    Minutes,
    Risk,
    build_minutes,
    render_minutes_markdown,
    split_words,
)
from packages.meetings.transcribe import Segment, Transcript, format_timestamp


class FakeModel:
    """Devuelve una extracción JSON por bloque y registra los prompts."""

    def __init__(self, parts: list[dict], summary: str = "Resumen global") -> None:
        self.parts = list(parts)
        self.summary = summary
        self.prompts: list[tuple[str, dict]] = []

    async def generate(self, prompt: str, **kwargs) -> InferenceResult:
        self.prompts.append((prompt, kwargs))
        text = json.dumps(self.parts.pop(0)) if "format" in kwargs else self.summary
        return InferenceResult(
            text=text,
            model="m",
            provider="fake",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
        )


def _part(**overrides) -> dict:
    base = {
        "titulo": "Seguimiento",
        "resumen": "Se revisó el estado.",
        "asistentes": ["Ana Pérez"],
        "temas": ["Datos maestros"],
        "decisiones": [],
        "acciones": [],
        "riesgos": [],
        "proxima_reunion": "",
    }
    return {**base, **overrides}


def test_split_words():
    assert split_words("a b c d e", size=2) == ["a b", "c d", "e"]
    assert split_words("") == [""]


async def test_single_chunk_uses_schema_and_meeting_date():
    model = FakeModel(
        [
            _part(
                acciones=[
                    {
                        "tarea": "Llamar al proveedor",
                        "responsable": "Luis",
                        "fecha_limite": "2026-09-25",
                    },
                    {"tarea": "Sin fecha válida", "responsable": "", "fecha_limite": "el viernes"},
                ],
                riesgos=[
                    {
                        "riesgo": "Retraso",
                        "probabilidad": "Alta",
                        "impacto": "alto",
                        "mitigacion": "Exportación manual",
                    }
                ],
                proxima_reunion="2026-09-24 10:00",
            )
        ]
    )
    minutes = await build_minutes(
        model, "texto de la reunión", meeting_date=datetime.date(2026, 9, 17), project="ERP"
    )
    prompt, kwargs = model.prompts[0]
    assert "jueves 2026-09-17" in prompt and "Proyecto: ERP." in prompt
    assert kwargs["format"]["required"][0] == "titulo"
    assert minutes.titulo == "Seguimiento"
    assert minutes.resumen == "Se revisó el estado."
    assert minutes.acciones[0] == Action("Llamar al proveedor", "Luis", "2026-09-25", "")
    assert minutes.acciones[1].fecha_limite == ""
    assert minutes.riesgos[0].probabilidad == "alta"
    assert minutes.proxima_reunion == "2026-09-24 10:00"


async def test_long_meeting_merges_chunks_and_dedupes(monkeypatch):
    monkeypatch.setattr("packages.meetings.minutes.CHUNK_WORDS", 3)
    action = {"tarea": "Plan de formación", "responsable": "Ana", "fecha_limite": ""}
    model = FakeModel(
        [
            _part(resumen="Parte uno.", acciones=[action], decisiones=["Mantener fecha"]),
            _part(
                resumen="Parte dos.",
                acciones=[dict(action, tarea="plan de formación")],
                asistentes=["Ana Pérez", "Luis Gómez"],
                decisiones=["Mantener fecha"],
            ),
        ],
        summary="Resumen de toda la reunión.",
    )
    progress = []

    async def on_progress(done, total):
        progress.append((done, total))

    minutes = await build_minutes(
        model,
        "uno dos tres cuatro cinco seis",
        meeting_date=datetime.date(2026, 9, 17),
        title="Comité",
        on_progress=on_progress,
    )
    assert "parte 1 de 2" in model.prompts[0][0]
    assert minutes.titulo == "Comité"
    assert minutes.resumen == "Resumen de toda la reunión."
    assert [a.tarea for a in minutes.acciones] == ["Plan de formación"]
    assert minutes.decisiones == ["Mantener fecha"]
    assert minutes.asistentes == ["Ana Pérez", "Luis Gómez"]
    assert sorted(progress) == [(1, 2), (2, 2)]


def test_minutes_roundtrip_and_markdown():
    minutes = Minutes(
        titulo="Seguimiento",
        fecha="2026-09-17",
        resumen="Todo en plazo.",
        asistentes=["Ana"],
        decisiones=["Mantener el 1 de diciembre"],
        acciones=[Action("Plan | formación", "Ana", "2026-10-02", "")],
        riesgos=[Risk("Servidor sin memoria", "media", "alto", "Ampliar", "Luis")],
    )
    assert Minutes.from_dict(minutes.to_dict()) == minutes
    md = render_minutes_markdown(
        minutes, project="ERP", duration="00:01:26", transcript="[00:00:00] Hola"
    )
    assert md.startswith('---\ntitle: "Acta: Seguimiento"')
    assert "| 1 | Plan / formación | Ana | 2026-10-02 |" in md
    assert "| 1 | Servidor sin memoria | media | alto | Ampliar | Luis |" in md
    assert "## Temas tratados\n\nNinguno." in md
    assert md.rstrip().endswith("[00:00:00] Hola")


def test_transcript_paragraphs_with_timestamps():
    transcript = Transcript(
        language="es",
        duration_seconds=130,
        segments=[Segment(0, 30, "Hola."), Segment(30, 65, "Punto uno."), Segment(65, 130, "Fin.")],
    )
    assert transcript.text == "Hola. Punto uno. Fin."
    assert transcript.with_timestamps() == "[00:00:00] Hola. Punto uno.\n\n[00:01:05] Fin."
    assert format_timestamp(3725) == "01:02:05"


@pytest.mark.parametrize("raw", ['{"titulo": "x"}', 'Texto previo {"titulo": "x"} fin'])
def test_parse_tolerates_wrapped_json(raw):
    from packages.meetings.minutes import _parse

    assert _parse(raw) == {"titulo": "x"}
