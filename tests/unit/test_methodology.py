from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from apps.api.jarvis_api.scoping import scoped_filters
from packages.core.directives import (
    methodology_from_metadata,
    methodology_id,
    parse_directives,
    set_directive,
)
from packages.core.scope import Scope
from packages.rag.store import _build_filter

MEMORY = """# MEMORY.md — Directivas de Ana

## General

- Respuestas cortas.

## Metodologías

### Scrum
- Historias de usuario y sprints de dos semanas.

### PMI
- Acta de constitución antes de planificar.

### Cascada

## Proyectos

Una línea por proyecto: `- Empresa › Proyecto: Scrum`.
- Estudio Delta › App de reservas: Scrum
- Acme › Migración ERP: PMI + Scrum (híbrido pedido por Ana)
- Intranet: Cascada
- Sin método:
"""


def test_parse_directives_reads_zones():
    directives = parse_directives(MEMORY)
    assert directives.methods == ["Scrum", "PMI", "Cascada"]
    assert directives.for_project("Estudio Delta", "App de reservas") == ["scrum"]
    assert directives.for_project("acme", "migracion erp") == ["pmi", "scrum"]
    assert directives.labels[("acme", "migracion-erp")] == "Acme › Migración ERP"


def test_project_without_company_in_memory_matches_any_company():
    directives = parse_directives(MEMORY)
    assert directives.for_project("Globex", "Intranet") == ["cascada"]
    assert directives.for_project("", "Intranet") == ["cascada"]


def test_projects_without_methodology_get_none():
    directives = parse_directives(MEMORY)
    assert directives.for_project("Acme", "Sin método") == []
    assert directives.for_project("Acme", "Otro") == []
    assert directives.for_project("Acme", "") == []
    assert parse_directives("").for_project("Acme", "ERP") == []


def test_list_lines_outside_projects_zone_are_not_projects():
    directives = parse_directives("## General\n\n- Correo: siempre en borrador\n")
    assert directives.projects == {}


def test_methodology_metadata_and_ids():
    assert methodology_id("Scrum") == "scrum"
    assert methodology_id("PMI (PMBOK 7)") == "pmi-pmbok-7"
    assert methodology_id("") == ""
    assert methodology_from_metadata({"methodology": " Scrum "}) == "Scrum"
    assert methodology_from_metadata(None) == ""


def test_scoped_filters_adds_methodologies_only_when_given():
    scope = Scope("Acme", "ERP")
    assert "methodologies" not in scoped_filters({}, scope)["scope"]
    filters = scoped_filters({}, scope, ["PMI", "Scrum", "scrum", " "])
    assert filters["scope"]["methodologies"] == ["pmi", "scrum"]


@pytest.fixture
def qdrant():
    client = QdrantClient(":memory:")
    client.create_collection(
        "docs", vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE)
    )
    points = [
        ("pmbok", None, None, "pmi"),
        ("scrum-guide", None, None, "scrum"),
        ("iso-9001", None, None, None),
        ("acme-scrum-manual", "acme", None, "scrum"),
        ("globex-pmi", "globex", None, "pmi"),
        ("acme-erp-brief", "acme", "erp", None),
    ]
    client.upsert(
        "docs",
        [
            models.PointStruct(
                id=i,
                vector=[1.0],
                payload={"name": n, "company": c, "project": p, "methodology": m},
            )
            for i, (n, c, p, m) in enumerate(points)
        ],
    )
    return client


def _names(client: QdrantClient, scope: dict) -> set[str]:
    points, _ = client.scroll("docs", scroll_filter=_build_filter({"scope": scope}), limit=50)
    return {p.payload["name"] for p in points}  # type: ignore[index]


def test_scrum_project_does_not_see_other_methodologies(qdrant):
    scope = {"company": "acme", "project": "erp", "methodologies": ["scrum"]}
    assert _names(qdrant, scope) == {
        "scrum-guide",
        "iso-9001",
        "acme-scrum-manual",
        "acme-erp-brief",
    }


def test_mixing_is_explicit_and_keeps_company_isolation(qdrant):
    scope = {"company": "acme", "project": "erp", "methodologies": ["scrum", "pmi"]}
    names = _names(qdrant, scope)
    assert {"pmbok", "scrum-guide"} <= names
    assert "globex-pmi" not in names


def test_without_methodology_everything_in_scope_is_visible(qdrant):
    assert _names(qdrant, {"company": "acme", "project": "erp"}) == {
        "pmbok",
        "scrum-guide",
        "iso-9001",
        "acme-scrum-manual",
        "acme-erp-brief",
    }


TEMPLATE = (
    Path(__file__).resolve().parents[2] / "integrations/openclaw/workspace/MEMORY.md"
).read_text()


def test_set_directive_writes_each_zone_without_touching_others():
    text, section = set_directive(TEMPLATE, "metodologia", "PMI", "- Acta de constitución.")
    assert section == "### PMI\n- Acta de constitución."
    text, _ = set_directive(text, "metodologia", "Scrum", "- Sprints de dos semanas.")
    text, _ = set_directive(text, "proyecto", "Acme › ERP", "PMI")
    text, _ = set_directive(text, "proyecto", "Delta › App", "Scrum")
    text, _ = set_directive(text, "general", "Reuniones", "- 45 minutos.")
    directives = parse_directives(text)
    assert directives.methods == ["PMI", "Scrum"]
    assert directives.for_project("Acme", "ERP") == ["pmi"]
    assert directives.for_project("Delta", "App") == ["scrum"]
    general = text.split("## General")[1].split("## Metodologías")[0]
    assert "### Reuniones\n- 45 minutos." in general


def test_set_directive_overwrites_only_its_section():
    text, _ = set_directive(TEMPLATE, "metodologia", "PMI", "- Línea base.")
    text, _ = set_directive(text, "metodologia", "Scrum", "- Sprints de dos semanas.")
    text, _ = set_directive(text, "proyecto", "Acme › ERP", "PMI")
    text, section = set_directive(
        text, "metodologia", "scrum", "- Sprints de tres semanas.", replace_all=True
    )
    assert section == "### Scrum\n- Sprints de tres semanas."  # conserva el título
    assert "dos semanas" not in text and "- Línea base." in text
    text, _ = set_directive(text, "proyecto", "acme › erp", "PMI + Scrum")
    assert parse_directives(text).for_project("Acme", "ERP") == ["pmi", "scrum"]
    assert text.count("ERP:") == 1


def test_set_directive_removes_and_validates():
    text, _ = set_directive(TEMPLATE, "metodologia", "Kanban", "- WIP 3.")
    text, section = set_directive(text, "metodologia", "Kanban", "")
    assert section == "" and "Kanban" not in parse_directives(text).methods
    with pytest.raises(ValueError, match="Zona"):
        set_directive(TEMPLATE, "empresa", "Acme", "x")
    with pytest.raises(ValueError, match="metodología"):
        set_directive(TEMPLATE, "proyecto", "Acme › ERP", "(pendiente)")
    with pytest.raises(ValueError, match="larga"):
        set_directive(TEMPLATE, "general", "Todo", "x" * 3000)


def test_set_directive_keeps_zones_intact():
    text, _ = set_directive(TEMPLATE, "metodologia", "PMI", "## Fases\n- Inicio")
    assert "**Fases**" in text and text.count("\n## ") == TEMPLATE.count("\n## ")
    text, _ = set_directive("", "proyecto", "Acme › ERP", "PMI")
    assert parse_directives(text).for_project("Acme", "ERP") == ["pmi"]


def test_set_directive_merges_rules_by_key():
    rules = "- **Trabajo:** historias de usuario.\n- **Sprints:** de dos semanas.\n- Sin Gantt."
    text, _ = set_directive(TEMPLATE, "metodologia", "Scrum", rules)
    text, section = set_directive(text, "metodologia", "Scrum", "- Sprints: de tres semanas.")
    assert section.splitlines() == [
        "### Scrum",
        "- **Trabajo:** historias de usuario.",
        "- Sprints: de tres semanas.",
        "- Sin Gantt.",
    ]
    text, section = set_directive(text, "metodologia", "Scrum", "- Daily: 15 minutos.")
    assert section.endswith("- Sin Gantt.\n- Daily: 15 minutos.")
    text, section = set_directive(text, "metodologia", "Scrum", "- Kanban.", replace_all=True)
    assert section == "### Scrum\n- Kanban."
