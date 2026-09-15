import pytest

from packages.core.errors import ValidationFailedError
from packages.docgen.templates import build_sections_plan


def test_dafo_has_four_sections():
    sections = build_sections_plan("dafo", "Proyecto X")
    assert len(sections) == 4
    titles = [title for title, _ in sections]
    assert titles == ["Fortalezas", "Debilidades", "Oportunidades", "Amenazas"]
    for _, question in sections:
        assert "Proyecto X" in question


def test_plan_has_four_sections():
    sections = build_sections_plan("plan", "Proyecto X")
    assert len(sections) == 4
    titles = [title for title, _ in sections]
    assert titles == [
        "Objetivo y alcance",
        "Hitos y cronograma",
        "Riesgos identificados",
        "Responsables y stakeholders",
    ]
    for _, question in sections:
        assert "Proyecto X" in question


def test_resumen_has_four_sections():
    sections = build_sections_plan("resumen", "Guía del PMBOK")
    titles = [title for title, _ in sections]
    assert titles == [
        "Visión general",
        "Conceptos y principios clave",
        "Estructura y contenidos principales",
        "Aplicación práctica",
    ]
    for _, question in sections:
        assert "Guía del PMBOK" in question


def test_unknown_kind_raises_validation_error():
    with pytest.raises(ValidationFailedError):
        build_sections_plan("unknown", "Proyecto X")
