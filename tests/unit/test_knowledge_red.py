import datetime
from pathlib import Path

import pytest

from packages.knowledge import red
from packages.knowledge.red import Item, Snapshot

ACTA = """---
title: "Acta: Kick-off Tienda online"
date: 2026-03-02
---

<!-- openclaw:wiki:raw-source -->

# Acta: Kick-off Tienda online

- **Fecha:** 2026-03-02
- **Proyecto:** Tienda online
- **Asistentes:** Alex Gil (Jefe de proyecto), Eva Ruiz (Diseñadora)

## Acciones

| # | Tarea | Responsable | Fecha límite |
|---|---|---|---|
| 1 | Maquetas | Eva Ruiz | 2026-03-10 |
| 2 | Hosting | Alexx Gil | 2026-03-05 |
"""


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    acta = tmp_path / "sources/proyectos/tienda-online/actas/2026-03-02-kick-off.md"
    acta.parent.mkdir(parents=True)
    acta.write_text(ACTA, encoding="utf-8")
    return tmp_path


def _snapshot(vault: Path) -> Snapshot:
    snap = Snapshot(
        companies={"Ficticia SL": "https://op.example/projects/ficticia"},
        projects={
            "Tienda online": {
                "company": "Ficticia SL",
                "url": "https://op.example/projects/tienda",
                "gantt": "https://op.example/projects/tienda/gantt",
            }
        },
        milestones=[
            Item("7", "Lanzamiento", "Tienda online", "Ficticia SL", "2026-04-01", "Nuevo")
        ],
        risks=[
            Item(
                "8",
                "Retraso del proveedor: pagos",
                "Tienda online",
                "Ficticia SL",
                "",
                "Nuevo",
                ["Eva Ruiz"],
                "Probabilidad: media.",
            ),
        ],  # fmt: skip
        tasks=[
            Item(
                "9", "Maquetas", "Tienda online", "Ficticia SL", "2026-03-10", "Nuevo", ["Eva Ruiz"]
            ),
            Item("10", "Vieja", "Tienda online", "Ficticia SL", "", "Cerrado", ["Eva Ruiz"]),
        ],
        documents=[Item("uuid-1", "brief-tienda", "Tienda online", "Ficticia SL", "2026-03-01")],
    )
    snap.actas = red.read_actas(vault)
    for person, role in __import__("json").loads(snap.actas[0].detail).items():
        if role:
            snap.roles[person].add(role)
    red._merge_owner(snap, "Alex Gil")
    return snap


def test_read_actas_takes_attendees_roles_and_owners(vault):
    (acta,) = red.read_actas(vault)
    assert acta.id == "sources/proyectos/tienda-online/actas/2026-03-02-kick-off"
    assert acta.project == "Tienda online" and acta.date == "2026-03-02"
    assert acta.people == ["Alex Gil", "Eva Ruiz", "Eva Ruiz", "Alexx Gil"]
    # El rol de la lista de asistentes no se pierde al salir también como responsable.
    assert '"Eva Ruiz": "Diseñadora"' in acta.detail


def test_owner_variants_are_merged(vault):
    snap = _snapshot(vault)
    assert snap.actas[0].people == ["Alex Gil", "Eva Ruiz"]


PROJECT = "entities/empresas/Ficticia SL/Tienda online"


def test_pages_link_the_network(vault):
    pages = {p.path: p for p in red.build_pages(_snapshot(vault))}
    project = pages[PROJECT]
    assert "Proyecto de [[Ficticia SL]]" in project.body
    assert "[[Lanzamiento (OP-7)|Lanzamiento]]" in project.body
    assert "[[2026-03-02-kick-off|Acta: Kick-off Tienda online]]" in project.body
    assert "[[Eva Ruiz]] — Diseñadora" in project.body
    assert "Tareas abiertas (1)" in project.body  # la cerrada no cuenta
    assert project.front["relationships"][0]["targetId"] == "entity.empresa.ficticia-sl"
    person = pages["entities/personas/Eva Ruiz"]
    assert person.front["privacyTier"] == "private"
    assert "[[Tienda online]]" in person.body
    assert "entities/empresas/Ficticia SL" in pages
    assert "[[Ficticia SL]]" in pages[red.ROOT_NOTE].body


def test_tree_hangs_from_the_project_and_only_the_child_declares_it(vault):
    pages = {p.path: p for p in red.build_pages(_snapshot(vault))}
    # Los ":" no valen en un nombre de archivo.
    risk = pages[f"{PROJECT}/riesgos/Retraso del proveedor pagos (OP-8)"]
    assert "Riesgo de [[Tienda online]]" in risk.body and "[[Eva Ruiz]]" in risk.body
    assert risk.front["relationships"][0] == {
        "targetId": "entity.proyecto.tienda-online",
        "targetTitle": "Tienda online",
        "kind": "pertenece-a",
    }
    assert f"{PROJECT}/hitos/Lanzamiento (OP-7)" in pages
    # La empresa no repite la relación: la declara el proyecto con «pertenece-a».
    assert pages["entities/empresas/Ficticia SL"].front["relationships"] == []
    # Los documentos son de la red, no del árbol: los cruza el RAG entre proyectos.
    assert "entities/documentos/brief-tienda" in pages


def test_tasks_become_notes_only_when_they_weigh(vault):
    pages = {p.path: p for p in red.build_pages(_snapshot(vault))}
    # «Maquetas» la nombra el acta; «Vieja» no, así que se queda como línea del proyecto.
    assert f"{PROJECT}/tareas/Maquetas (OP-9)" in pages
    assert not any(path.endswith("/tareas/Vieja (OP-10)") for path in pages)
    assert "[[Maquetas (OP-9)|Maquetas]]" in pages[PROJECT].body


def test_concepts_index_projects_instead_of_every_item(vault):
    pages = {p.path: p for p in red.build_pages(_snapshot(vault))}
    risks = pages["concepts/Gestión de riesgos"]
    assert "[[Tienda online]] — 1 riesgo" in risks.body
    # Ningún ítem enlaza al concepto: era la arista que enmarañaba el grafo.
    risk = pages[f"{PROJECT}/riesgos/Retraso del proveedor pagos (OP-8)"]
    assert "[[Gestión de riesgos]]" not in risk.body


def test_write_keeps_human_notes_and_links_actas(vault):
    snap = _snapshot(vault)
    pages = red.build_pages(snap)
    assert red.write_pages(vault, pages, snap) > 0
    note = vault / f"{PROJECT}.md"
    note.write_text(note.read_text() + "\nMi nota a mano.\n", encoding="utf-8")
    red.write_pages(vault, pages, snap)
    assert note.read_text().endswith("Mi nota a mano.\n")
    assert red.write_pages(vault, pages, snap) == 0  # sin cambios, no reescribe
    acta = (vault / f"{snap.actas[0].id}.md").read_text()
    assert "Proyecto: [[Tienda online]]" in acta and "[[Alex Gil]]" in acta
    assert acta.count(red.START) == 1


def test_flat_notes_are_moved_into_the_tree(vault):
    """Migración de la estructura plana anterior, con lo que hubieras escrito tú."""
    snap = _snapshot(vault)
    old = vault / "entities/proyectos/Tienda online.md"
    old.parent.mkdir(parents=True)
    old.write_text(
        f'---\ngeneratedBy: "jarvis-red"\n---\n\n{red.START}\nviejo\n{red.END}\n\n'
        "## Notas\n- 2026-03-03: ojo con el proveedor.\n",
        encoding="utf-8",
    )
    red.write_pages(vault, red.build_pages(snap), snap)

    moved = (vault / f"{PROJECT}.md").read_text()
    assert "- 2026-03-03: ojo con el proveedor." in moved
    assert "Proyecto de [[Ficticia SL]]" in moved and "viejo" not in moved
    assert not old.exists() and not old.parent.exists()  # la carpeta plana vacía se retira


def test_human_note_with_same_name_is_not_touched(vault):
    snap = _snapshot(vault)
    human = vault / "entities/empresas/Ficticia SL.md"
    human.parent.mkdir(parents=True)
    human.write_text("# Mía\n", encoding="utf-8")
    red.write_pages(vault, red.build_pages(snap), snap)
    assert human.read_text() == "# Mía\n"


def test_remember_appends_outside_generated_block(vault):
    snap = _snapshot(vault)
    red.write_pages(vault, red.build_pages(snap), snap)
    day = datetime.date(2026, 3, 3)
    note = red.remember(vault, "tienda ONLINE", "Prefiere  reuniones\npor la mañana", day)
    red.remember(vault, "Tienda online", "Pago con Bizum", day)
    text = note.read_text()
    assert text.index(red.END) < text.index("## Notas")
    assert "- 2026-03-03: Prefiere reuniones por la mañana\n- 2026-03-03: Pago con Bizum" in text
    red.write_pages(vault, red.build_pages(snap), snap)  # regenerar no la borra
    assert "Pago con Bizum" in note.read_text()
    with pytest.raises(LookupError, match="Hay:"):
        red.remember(vault, "Otra cosa", "x")


def test_remember_creates_person_or_topic_only_when_asked(vault):
    day = datetime.date(2026, 3, 3)
    with pytest.raises(LookupError, match="new='persona'"):
        red.remember(vault, "Carmen", "Le gusta Marvel", day)
    person = red.remember(vault, "Carmen", "Le gusta Marvel", day, new="persona")
    assert person == vault / "entities/personas/Carmen.md"
    topic = red.remember(vault, "Metodología de trabajo", "PMBOK y Snyder", day, new="tema")
    assert topic == vault / "memoria/Metodología de trabajo.md"
    red.remember(vault, "metodologia", "Arquitecto y Operador", day)  # ya existe: la encuentra
    assert topic.read_text().count("- 2026-03-03:") == 2
    with pytest.raises(LookupError, match="'persona' o 'tema'"):
        red.remember(vault, "Otra", "x", day, new="empresa")


def test_generated_person_keeps_notes_written_by_remember(vault):
    """Si la red genera después a esa persona, rellena el bloque y respeta las notas."""
    snap = _snapshot(vault)
    red.remember(vault, "Alex Gil", "Prefiere correo", datetime.date(2026, 3, 3), new="persona")
    red.write_pages(vault, red.build_pages(snap), snap)
    text = (vault / "entities/personas/Alex Gil.md").read_text()
    assert "generatedBy" in text and "[[Tienda online]]" in text
    assert text.index(red.END) < text.index("- 2026-03-03: Prefiere correo")


def test_directives_are_mirrored_and_not_rememberable(vault, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert not red.mirror_directives(workspace, vault)  # sin MEMORY.md no hace nada
    (workspace / "MEMORY.md").write_text("# Directivas\n\n- Arquitecto y Operador\n")
    assert red.mirror_directives(workspace, vault)
    assert not red.mirror_directives(workspace, vault)  # sin cambios no reescribe
    note = vault / f"{red.DIRECTIVES_NOTE}.md"
    assert "- Arquitecto y Operador" in note.read_text()
    with pytest.raises(LookupError):
        red.remember(vault, "Directivas de Jarvis", "x")
    with pytest.raises(LookupError, match="MEMORY.md"):
        red.remember(vault, "Directivas de Jarvis", "x", new="tema")


def test_note_name_is_safe():
    assert red.note_name('Riesgo: "pagos" #1 / [x]') == "Riesgo pagos 1 x"
    assert red.note_name("a" * 100) == "a" * 80
