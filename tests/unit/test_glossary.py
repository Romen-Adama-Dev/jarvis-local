from collections import Counter

from packages import glossary
from packages.glossary import SOURCES, describe, find_in, load, lookup, translation_hints


def test_every_term_is_complete_and_cites_a_known_source():
    terms = load()
    assert len(terms) > 400
    areas = Counter(t.area for t in terms)
    assert {"Dirección de proyectos", "Scrum", "Kanban", "Lean", "Ágil"} <= set(areas)
    for term in terms:
        assert term.es and term.en and term.definition.endswith("."), term
        assert term.sources and set(term.sources) <= set(SOURCES), term


def test_no_term_is_listed_twice():
    pairs = Counter((glossary._key(t.name), glossary._key(t.english)) for t in load())
    assert [pair for pair, n in pairs.items() if n > 1] == []


def test_official_equivalences():
    def english(name: str) -> str:
        return lookup(name)[0].english

    assert english("acta de constitución del proyecto") == "Project charter"
    assert english("EDT") == "Work breakdown structure"
    assert english("holgura") == "Float"
    assert english("pila del producto") == "Product Backlog"
    assert english("trabajo en curso") == "Work in progress"
    assert lookup("Definition of Done")[0].name == "Definición de terminado"
    assert "Definición de hecho" in lookup("DoD")[0].es  # la de la Guía de Scrum


def test_find_prefers_the_longest_term():
    found = [t.name for t in find_in("¿Qué lleva el acta de constitución del proyecto?")]
    assert found == ["Acta de constitución del proyecto"]


def test_acronyms_only_count_in_capitals():
    assert [t.english for t in find_in("calcula el SPI")] == ["Schedule performance index"]
    assert find_in("spi") == []


def test_translation_hints_skip_generic_identical_and_ambiguous_words():
    assert translation_hints("riesgo del proyecto") == ""  # palabras generales
    assert translation_hints("el sprint de Scrum") == ""  # se escriben igual
    assert translation_hints("la entrega del viernes") == ""  # «entrega»: dos términos
    hints = translation_hints("ruta crítica y holgura total de las actividades")
    assert hints == "Ruta crítica = Critical path; Holgura = Float"


def test_lookup_partial_and_fuzzy():
    assert lookup("ruta critca")[0].name == "Ruta crítica"  # error tecleando
    assert lookup("takt")[0].name == "Takt time"
    assert lookup("palabra que no existe") == []
    text = describe(lookup("EVM")[0])
    assert "Earned value management" in text and "Fuente:" in text
