"""Acta de reunión a partir de la transcripción, con el modelo local de Ollama.

La transcripción se trocea en bloques (~5.000 palabras, unos 8.000 tokens) y de cada uno
se extrae en JSON, con esquema impuesto por Ollama: resumen, temas, decisiones, acciones
(responsable y fecha), riesgos (probabilidad, impacto, mitigación) y asistentes. Luego se
unen los bloques quitando duplicados y, si hubo más de uno, se redacta un resumen global.
Así una reunión de varias horas no desborda el contexto del modelo.

Las fechas relativas ("el viernes") se convierten a AAAA-MM-DD con la fecha de la reunión.
"""

import asyncio
import datetime
import json
import re
import subprocess
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from packages.core.errors import ProviderUnavailableError
from packages.core.logging import get_logger
from packages.inference.base import InferenceResult

logger = get_logger(__name__)

CHUNK_WORDS = 5000
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class ChatModel(Protocol):
    async def generate(self, prompt: str, **kwargs: Any) -> InferenceResult: ...


@dataclass
class Action:
    tarea: str
    responsable: str = ""
    fecha_limite: str = ""
    detalle: str = ""


@dataclass
class Risk:
    riesgo: str
    probabilidad: str = ""
    impacto: str = ""
    mitigacion: str = ""
    responsable: str = ""


@dataclass
class Minutes:
    titulo: str
    fecha: str
    resumen: str
    asistentes: list[str] = field(default_factory=list)
    temas: list[str] = field(default_factory=list)
    decisiones: list[str] = field(default_factory=list)
    acciones: list[Action] = field(default_factory=list)
    riesgos: list[Risk] = field(default_factory=list)
    proxima_reunion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Minutes":
        return cls(
            titulo=data.get("titulo", ""),
            fecha=data.get("fecha", ""),
            resumen=data.get("resumen", ""),
            asistentes=list(data.get("asistentes", [])),
            temas=list(data.get("temas", [])),
            decisiones=list(data.get("decisiones", [])),
            acciones=[Action(**a) for a in data.get("acciones", [])],
            riesgos=[Risk(**r) for r in data.get("riesgos", [])],
            proxima_reunion=data.get("proxima_reunion", ""),
        )


_STR_LIST = {"type": "array", "items": {"type": "string"}}
EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "resumen": {"type": "string"},
        "asistentes": _STR_LIST,
        "temas": _STR_LIST,
        "decisiones": _STR_LIST,
        "acciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tarea": {"type": "string"},
                    "responsable": {"type": "string"},
                    "fecha_limite": {"type": "string"},
                    "detalle": {"type": "string"},
                },
                "required": ["tarea", "responsable", "fecha_limite"],
            },
        },
        "riesgos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "riesgo": {"type": "string"},
                    "probabilidad": {"type": "string", "enum": ["alta", "media", "baja", ""]},
                    "impacto": {"type": "string", "enum": ["alto", "medio", "bajo", ""]},
                    "mitigacion": {"type": "string"},
                    "responsable": {"type": "string"},
                },
                "required": ["riesgo", "probabilidad", "impacto", "mitigacion"],
            },
        },
        "proxima_reunion": {"type": "string"},
    },
    "required": [
        "titulo",
        "resumen",
        "asistentes",
        "temas",
        "decisiones",
        "acciones",
        "riesgos",
        "proxima_reunion",
    ],
}

_EXTRACT_PROMPT = """Eres el secretario de una reunión de proyecto. Te paso {part} de la \
transcripción automática (puede tener errores de reconocimiento: corrígelos por contexto).
La reunión fue el {weekday} {date}.{project_line}

Extrae en JSON, en español y solo con lo que se dice de verdad (no inventes):
- titulo: título corto de la reunión.
- resumen: 3-6 frases con lo esencial.
- asistentes: nombres (y rol si se dice) de quienes participan.
- temas: puntos tratados, una frase cada uno.
- decisiones: acuerdos cerrados.
- acciones: tareas encargadas a alguien. "responsable": nombre de quien la hará (también
  si "se encarga", "se ofrece" o se le asigna) o "" si no se dice.
  "fecha_limite": AAAA-MM-DD (convierte "el viernes", "el 25", "fin de mes" usando la
  fecha de la reunión) o "" si no hay. "detalle": contexto útil para quien la haga.
- riesgos: amenazas o problemas que pueden afectar al proyecto, con probabilidad (alta,
  media, baja), impacto (alto, medio, bajo), mitigación acordada y responsable, o "" si
  no se dice.
- proxima_reunion: fecha y hora si se acuerda, o "".
Listas vacías si no hay nada de ese tipo.

TRANSCRIPCIÓN:
{text}"""

_SUMMARY_PROMPT = """Estos son los resúmenes parciales, en orden, de una reunión de \
proyecto larga. Redacta un único resumen ejecutivo de 5-8 frases, en español, sin \
repetir ideas y sin inventar nada:

{parts}"""


def split_words(text: str, size: int | None = None) -> list[str]:
    size = size or CHUNK_WORDS
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)] or [""]


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _dedupe(items: list, key) -> list:
    seen: set[str] = set()
    out = []
    for item in items:
        k = _key(key(item))
        if k and k not in seen:
            seen.add(k)
            out.append(item)
    return out


def _valid_date(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value.strip()).isoformat()
    except (ValueError, AttributeError):
        return ""


def _parse(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group(0)) if match else {}


async def _extract(
    model: ChatModel, text: str, part: str, date: datetime.date, project: str
) -> dict:
    prompt = _EXTRACT_PROMPT.format(
        part=part,
        weekday=_WEEKDAYS[date.weekday()],
        date=date.isoformat(),
        project_line=f"\nProyecto: {project}." if project else "",
        text=text,
    )
    result = await model.generate(prompt, format=EXTRACT_SCHEMA, temperature=0.1)
    return _parse(result.text)


async def build_minutes(
    model: ChatModel,
    transcript_text: str,
    *,
    meeting_date: datetime.date,
    title: str = "",
    project: str = "",
    concurrency: int = 2,
    on_progress=None,
) -> Minutes:
    chunks = split_words(transcript_text)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    done = 0

    async def run(index: int, chunk: str) -> dict:
        nonlocal done
        part = (
            "la transcripción completa"
            if len(chunks) == 1
            else (f"la parte {index + 1} de {len(chunks)}")
        )
        async with semaphore:
            data = await _extract(model, chunk, part, meeting_date, project)
        done += 1
        if on_progress:
            await on_progress(done, len(chunks))
        return data

    parts = await asyncio.gather(*(run(i, c) for i, c in enumerate(chunks)))
    logger.info("meeting_minutes_extracted", chunks=len(chunks))

    actions = [
        Action(
            tarea=a.get("tarea", "").strip(),
            responsable=a.get("responsable", "").strip(),
            fecha_limite=_valid_date(a.get("fecha_limite", "")),
            detalle=a.get("detalle", "").strip(),
        )
        for p in parts
        for a in p.get("acciones", [])
        if a.get("tarea", "").strip()
    ]
    risks = [
        Risk(
            riesgo=r.get("riesgo", "").strip(),
            probabilidad=r.get("probabilidad", "").strip().lower(),
            impacto=r.get("impacto", "").strip().lower(),
            mitigacion=r.get("mitigacion", "").strip(),
            responsable=r.get("responsable", "").strip(),
        )
        for p in parts
        for r in p.get("riesgos", [])
        if r.get("riesgo", "").strip()
    ]

    def collect(name: str) -> list[str]:
        values = [str(v).strip() for p in parts for v in p.get(name, []) if str(v).strip()]
        return _dedupe(values, lambda v: v)

    summaries = [p.get("resumen", "").strip() for p in parts if p.get("resumen", "").strip()]
    if len(summaries) > 1:
        joined = "\n\n".join(f"Parte {i + 1}: {s}" for i, s in enumerate(summaries))
        summary = (await model.generate(_SUMMARY_PROMPT.format(parts=joined))).text.strip()
    else:
        summary = summaries[0] if summaries else ""

    next_meetings = [p["proxima_reunion"] for p in parts if p.get("proxima_reunion")]
    next_meeting = next_meetings[-1] if next_meetings else ""
    return Minutes(
        titulo=title or next((p["titulo"] for p in parts if p.get("titulo")), "Reunión"),
        fecha=meeting_date.isoformat(),
        resumen=summary,
        asistentes=collect("asistentes"),
        temas=collect("temas"),
        decisiones=collect("decisiones"),
        acciones=_dedupe(actions, lambda a: a.tarea),
        riesgos=_dedupe(risks, lambda r: r.riesgo),
        proxima_reunion=next_meeting,
    )


def _cell(text: str) -> str:
    return (text or "—").replace("|", "/").replace("\n", " ")


def render_minutes_markdown(
    minutes: Minutes,
    *,
    project: str = "",
    duration: str = "",
    transcript: str = "",
) -> str:
    """Acta en Markdown (sirve para Obsidian, el RAG y, con pandoc, PDF o Word)."""
    lines = [
        "---",
        f'title: "Acta: {minutes.titulo}"',
        "lang: es",
        f"date: {minutes.fecha}",
        "---",
        "",
        f"# Acta: {minutes.titulo}",
        "",
        f"- **Fecha:** {minutes.fecha}",
    ]
    if project:
        lines.append(f"- **Proyecto:** {project}")
    if duration:
        lines.append(f"- **Duración de la grabación:** {duration}")
    if minutes.asistentes:
        lines.append(f"- **Asistentes:** {', '.join(minutes.asistentes)}")
    lines += [
        "",
        "> Acta generada por Jarvis a partir de la grabación. Revísala antes de distribuirla.",
        "",
        "## Resumen",
        "",
        minutes.resumen or "—",
        "",
    ]

    def bullets(title: str, items: list[str]) -> None:
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {i}" for i in items] or ["Ninguno."])
        lines.append("")

    bullets("Temas tratados", minutes.temas)
    bullets("Decisiones", minutes.decisiones)

    lines += ["## Acciones", ""]
    if minutes.acciones:
        lines += ["| # | Tarea | Responsable | Fecha límite |", "|---|---|---|---|"]
        for n, a in enumerate(minutes.acciones, start=1):
            task = _cell(a.tarea + (f" ({a.detalle})" if a.detalle else ""))
            lines.append(f"| {n} | {task} | {_cell(a.responsable)} | {_cell(a.fecha_limite)} |")
    else:
        lines.append("Ninguna.")
    lines.append("")

    lines += ["## Riesgos", ""]
    if minutes.riesgos:
        lines += [
            "| # | Riesgo | Probabilidad | Impacto | Mitigación | Responsable |",
            "|---|---|---|---|---|---|",
        ]
        for n, r in enumerate(minutes.riesgos, start=1):
            lines.append(
                f"| {n} | {_cell(r.riesgo)} | {_cell(r.probabilidad)} | {_cell(r.impacto)} "
                f"| {_cell(r.mitigacion)} | {_cell(r.responsable)} |"
            )
    else:
        lines.append("Ninguno.")
    lines.append("")

    if minutes.proxima_reunion:
        lines += ["## Próxima reunión", "", minutes.proxima_reunion, ""]
    if transcript:
        lines += ["## Anexo: transcripción", "", transcript, ""]
    return "\n".join(lines)


def render_docx_via_pandoc(markdown_path: Path, out_path: Path) -> None:
    """Acta en Word: pandoc convierte el Markdown (con sus tablas) sin LaTeX."""
    try:
        subprocess.run(
            ["pandoc", str(markdown_path), "-o", str(out_path), "-V", "lang=es"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or str(exc)
        raise ProviderUnavailableError(f"pandoc falló al generar el Word: {stderr[:2000]}") from exc
