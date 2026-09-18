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


def test_pages_link_the_network(vault):
    pages = {p.path: p for p in red.build_pages(_snapshot(vault))}
    project = pages["entities/proyectos/Tienda online"]
    assert "Proyecto de [[Ficticia SL]]" in project.body
    assert "[[Lanzamiento (OP-7)|Lanzamiento]]" in project.body
    assert "[[2026-03-02-kick-off|Acta: Kick-off Tienda online]]" in project.body
    assert "[[Eva Ruiz]] — Diseñadora" in project.body
    assert "Tareas abiertas (1)" in project.body  # la cerrada no cuenta
    assert project.front["relationships"][0]["targetId"] == "entity.empresa.ficticia-sl"
    # Los ":" no valen en un nombre de archivo.
    risk = pages["entities/riesgos/Retraso del proveedor pagos (OP-8)"]
    assert "[[Gestión de riesgos]]" in risk.body and "[[Eva Ruiz]]" in risk.body
    person = pages["entities/personas/Eva Ruiz"]
    assert person.front["privacyTier"] == "private"
    assert "[[Tienda online]]" in person.body
    assert "entities/empresas/Ficticia SL" in pages
    assert "concepts/Gestión de riesgos" in pages
    assert "[[Ficticia SL]]" in pages[red.ROOT_NOTE].body


def test_write_keeps_human_notes_and_links_actas(vault):
    snap = _snapshot(vault)
    pages = red.build_pages(snap)
    assert red.write_pages(vault, pages, snap) > 0
    note = vault / "entities/proyectos/Tienda online.md"
    note.write_text(note.read_text() + "\nMi nota a mano.\n", encoding="utf-8")
    red.write_pages(vault, pages, snap)
    assert note.read_text().endswith("Mi nota a mano.\n")
    assert red.write_pages(vault, pages, snap) == 0  # sin cambios, no reescribe
    acta = (vault / f"{snap.actas[0].id}.md").read_text()
    assert "Proyecto: [[Tienda online]]" in acta and "[[Alex Gil]]" in acta
    assert acta.count(red.START) == 1


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


def test_note_name_is_safe():
    assert red.note_name('Riesgo: "pagos" #1 / [x]') == "Riesgo pagos 1 x"
    assert red.note_name("a" * 100) == "a" * 80
