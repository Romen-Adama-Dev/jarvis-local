import datetime
import json

import pytest

from packages.inference.base import InferenceResult
from packages.meetings.minutes import build_minutes
from packages.meetings.transcribe import BASE_VOCABULARY, vocabulary_prompt
from packages.meetings.vocabulario import (
    contexto_proyecto,
    corregir_nombres,
    fonetica,
    nombres_de,
    prompt_whisper,
    vocabulario_acta,
)


class FakeOpenProject:
    def __init__(self, fail_find: bool = False) -> None:
        self.fail_find = fail_find
        self.searched: list[str] = []

    def find_project(self, name: str) -> dict:
        self.searched.append(name)
        if self.fail_find:
            raise LookupError(name)
        return {"id": 7, "name": "SGA"}

    def assignees(self, project_id: int) -> list[dict]:
        assert project_id == 7
        return [{"name": "Laura Méndez"}, {"name": "David Rivas"}]

    def work_packages(self, project: dict, *, only_open: bool = True) -> list[dict]:
        assert not only_open  # también lo cerrado: las sedes ya arrancadas siguen saliendo
        return [
            {"subject": "Arranque en Arinaga (Gran Canaria)"},
            {"subject": "Formación de usuarios en Las Chafiras"},
            {"subject": "Integración con Business Central"},
            {"subject": "Migración de datos maestros"},
        ]


def test_fonetica_hears_like_a_canarian():
    assert fonetica("Cebadal") == fonetica("Sebadal")  # seseo
    assert fonetica("Haringa") == "aringa"  # h muda
    assert fonetica("Valverde") == fonetica("Balberde")
    assert fonetica("Gestión").startswith("j") and fonetica("Miguel") == "migel"


def test_names_skip_the_capital_at_the_start_of_a_sentence():
    nombres = nombres_de(
        [
            "Formación de usuarios en Las Chafiras",
            "Hito: Arranque Lanzarote",
            "Arinaga: hipercuidado",
        ]
    )
    assert nombres == ["Las Chafiras", "Lanzarote", "Arinaga"]


def test_project_context_has_company_team_and_places():
    client = FakeOpenProject()
    contexto = contexto_proyecto(client, "Dielca", "SGA")
    assert client.searched == ["Dielca › SGA"]
    assert contexto[:4] == ["Dielca", "SGA", "Laura Méndez", "David Rivas"]
    assert {"Arinaga", "Gran Canaria", "Las Chafiras", "Business Central"} <= set(contexto)
    assert "Formación" not in contexto and "Migración" not in contexto


def test_project_context_without_openproject_keeps_what_it_knows():
    assert contexto_proyecto(None, "Dielca", "SGA") == ["Dielca", "SGA"]
    assert contexto_proyecto(FakeOpenProject(fail_find=True), "Dielca", "SGA") == ["Dielca", "SGA"]


def test_whisper_prompt_puts_the_project_last_and_fits_the_window():
    prompt = prompt_whisper(["Dielca", "Arinaga", "Laura Méndez"], "Pablo Vidal", BASE_VOCABULARY)
    assert prompt.startswith("Jarvis, OpenProject")
    assert prompt.endswith("Dielca, Arinaga, Laura Méndez, Pablo Vidal.")
    assert prompt.count("Arinaga") == 1  # el topónimo fijo no se repite
    assert "Las Chafiras" in prompt and "IGIC" in prompt and "guagua" in prompt


def test_whisper_prompt_drops_canarian_terms_before_the_base_and_the_team():
    equipo = [f"Persona {i:02d} Apellido{i:02d}" for i in range(25)]
    prompt = prompt_whisper(equipo, "", BASE_VOCABULARY)
    assert len(prompt) <= 901 and prompt.startswith(BASE_VOCABULARY)
    assert "Gran Canaria" in prompt and "Cabildo" not in prompt
    assert prompt.endswith(", ".join(equipo) + ".")


def test_whisper_prompt_never_cuts_a_name_in_half():
    larguísimo = [f"Nombre{i:03d} De Proyecto" for i in range(80)]
    prompt = prompt_whisper(larguísimo)
    assert (
        len(prompt) <= 901
        and prompt.startswith("Nombre")
        and prompt.endswith("Nombre079 De Proyecto.")
    )


def test_vocabulary_prompt_keeps_the_base_and_the_owner_names():
    prompt = vocabulary_prompt("Talleres Norte, Gijón")
    assert prompt.startswith(BASE_VOCABULARY) and prompt.endswith("Talleres Norte, Gijón.")
    assert "Arinaga" in prompt and "Fuerteventura" in prompt


@pytest.mark.parametrize(
    ("oido", "correcto"),
    [
        ("Haringa", "Arinaga"),
        ("Arinata", "Arinaga"),
        ("Cebadal", "Sebadal"),
        ("Chafira", "Chafiras"),
    ],
)
def test_misheard_project_names_are_fixed(oido, correcto):
    nombres = ["Dielca", "Arinaga", "El Sebadal", "Las Chafiras", "Laura Méndez"]
    assert corregir_nombres(f"El lunes arrancamos en {oido} con Laura.", nombres) == (
        f"El lunes arrancamos en {correcto} con Laura."
    )


def test_normal_words_and_other_places_are_left_alone():
    nombres = [
        "Dielca",
        "Arinaga",
        "El Sebadal",
        "Las Chafiras",
        "Laura Méndez",
        "Business Central",
    ]
    texto = (
        "Bueno, Entonces el Martes vamos a Agüimes y a Telde. Perfecto, Arrancamos con Marta, "
        "la Central de compras y el Centro de Arucas. Gracias."
    )
    assert corregir_nombres(texto, nombres) == texto
    assert corregir_nombres("Haringa", []) == "Haringa"


def test_minutes_vocabulary_starts_with_the_project():
    vocabulario = vocabulario_acta(["Dielca", "Arinaga"], limite=10)
    assert vocabulario[:3] == ["Dielca", "Arinaga", "Gran Canaria"] and len(vocabulario) == 10


class FakeModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> InferenceResult:
        self.prompts.append(prompt)
        payload = {"titulo": "Seguimiento", "resumen": "Estado.", "asistentes": [], "temas": []}
        return InferenceResult(
            text=json.dumps(payload) if "format" in kwargs else "Resumen",
            model="m",
            provider="fake",
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
        )


async def test_minutes_prompt_lists_the_names_to_spell():
    model = FakeModel()
    await build_minutes(
        model,
        "[00:00] Arrancamos en Arinaga el lunes.",
        meeting_date=datetime.date(2026, 10, 21),
        project="Dielca › SGA",
        vocabulary=["Dielca", "Arinaga", "Las Chafiras"],
    )
    assert "Nombres propios que pueden salir" in model.prompts[0]
    assert "Dielca, Arinaga, Las Chafiras." in model.prompts[0]
