import pytest

from packages.rag.orchestrator import _abstention


def test_mark_is_detected_and_removed():
    assert _abstention("SIN_EVIDENCIA: Los documentos no hablan del gofio escaldado.") == (
        True,
        "Los documentos no hablan del gofio escaldado.",
    )


@pytest.mark.parametrize(
    "text",
    [
        "No cuento con información suficiente en los documentos para responder.",
        "Lo siento, no tengo datos sobre el gofio escaldado en el contexto.",
        "El contexto proporcionado no contiene información sobre recetas.",
        "No he encontrado nada en los documentos sobre eso.",
    ],
)
def test_obvious_abstention_without_mark(text):
    assert _abstention(text) == (True, text)


@pytest.mark.parametrize(
    "text",
    [
        "El acta de constitución autoriza el proyecto [libro.pdf p. 3]. No hay información "
        "sobre plazos.",
        "Según el PMBOK, el riesgo se gestiona en todo el ciclo de vida.",
        "No hay que confundir riesgo con incidencia: un riesgo es incierto.",
    ],
)
def test_answers_that_only_mention_gaps_are_not_abstentions(text):
    assert _abstention(text) == (False, text)
