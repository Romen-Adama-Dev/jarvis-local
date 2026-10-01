import datetime
import json
import re
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

MEMORY = """# MEMORY.md

## General

## Metodologías

### Scrum
- Sprints de dos semanas.
#### Ceremonias
- Daily de 15 minutos.

## Proyectos

- Ficticia SL › Tienda online: Scrum
"""

EMPRESAS = "entities/Empresas"
FICTICIA = f"{EMPRESAS}/Ficticia SL"
TIENDA = f"{FICTICIA}/Tienda online"
OTRA = f"{EMPRESAS}/Otra SA"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    acta = tmp_path / "sources/proyectos/tienda-online/actas/2026-03-02-kick-off.md"
    acta.parent.mkdir(parents=True)
    acta.write_text(ACTA, encoding="utf-8")
    return tmp_path


def _snapshot(vault: Path) -> Snapshot:
    snap = Snapshot(
        companies={"Ficticia SL": "https://op.example/projects/ficticia", "Otra SA": ""},
        projects={
            "Tienda online": {
                "company": "Ficticia SL",
                "url": "https://op.example/projects/tienda",
                "gantt": "https://op.example/projects/tienda/gantt",
            },
            "Intranet": {"company": "Otra SA", "url": "", "gantt": ""},
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
        ],
        tasks=[
            Item(
                "9", "Maquetas", "Tienda online", "Ficticia SL", "2026-03-10", "Nuevo", ["Eva Ruiz"]
            ),
            Item("10", "Vieja", "Tienda online", "Ficticia SL", "", "Cerrado", ["Eva Ruiz"]),
            # Carmen trabaja con las dos empresas: es un nexo.
            Item("11", "Auditoría", "Tienda online", "Ficticia SL", "", "Nuevo", ["Carmen"]),
            Item("12", "Migrar correo", "Intranet", "Otra SA", "", "En espera", ["Carmen"]),
        ],
        meetings=[
            Item("3", "Kick-off", "Tienda online", "Ficticia SL", "2026-03-02", "celebrada"),
            Item("4", "Café con Leo", "", "", "2026-03-05", "convocada", ["Leo"]),
        ],
        documents=[
            Item("uuid-1", "Brief tienda", "Tienda online", "Ficticia SL", "2026-03-01"),
            Item("uuid-2", "Guía Scrum", date="2026-01-01", methodology="Scrum"),
            Item("uuid-3", "Manual de estilo", date="2026-01-02"),
        ],
        owner="Alex Gil",
    )
    snap.actas = red.read_actas(vault)
    snap.actas[0].company = "Ficticia SL"
    for person, role in json.loads(snap.actas[0].detail).items():
        if role:
            snap.roles[person].add(role)
    red._merge_owner(snap, "Alex Gil")
    red._read_knowledge(snap, vault, MEMORY)
    snap.has_directives = True
    return snap


def _pages(vault: Path) -> dict[str, red.Page]:
    return {p.path: p for p in red.build_pages(_snapshot(vault))}


def _links(body: str) -> set[str]:
    return set(re.findall(r"\[\[([^\]|]+)", body))


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


def test_the_tree_hangs_from_the_core(vault):
    pages = _pages(vault)
    core = pages[red.CORE]
    assert f"{EMPRESAS}/🗂 Empresas" in _links(core.body)
    assert "concepts/Conocimiento/📚 Conocimiento" in _links(core.body)
    assert "```mermaid" in core.body and "Propietario: Alex Gil" in core.body
    company = pages[f"{FICTICIA}/🏢 Ficticia SL"]
    assert company.front["relationships"] == []  # la relación la declara el hijo
    assert f"{TIENDA}/📁 Tienda online" in _links(company.body)
    project = pages[f"{TIENDA}/📁 Tienda online"]
    assert project.front["relationships"][0]["targetId"] == "entity.empresa.ficticia-sl"
    assert "Metodología: Scrum" in project.body
    assert f"{TIENDA}/Riesgos/⚠️ Riesgos de Tienda online" in _links(project.body)


def test_leaves_only_link_their_parent(vault):
    pages = _pages(vault)
    # Los ":" no valen en un nombre de archivo; la hoja cuelga del grupo de su proyecto.
    risk = pages[f"{TIENDA}/Riesgos/⚠️ Retraso del proveedor pagos"]
    assert _links(risk.body) == {f"{TIENDA}/Riesgos/⚠️ Riesgos de Tienda online"}
    assert "- **Responsable:** Eva Ruiz" in risk.body  # la persona va en texto
    assert risk.front["id"] == "entity.riesgo.op-8"
    assert {
        "targetId": "entity.persona.eva-ruiz",
        "targetTitle": "Eva Ruiz",
        "kind": "responsable",
    } in risk.front["relationships"]
    assert f"{TIENDA}/Hitos/🏁 Lanzamiento" in pages
    assert f"{TIENDA}/Reuniones/📅 2026-03-02 · Kick-off" in pages


def test_tasks_become_notes_only_when_they_weigh(vault):
    pages = _pages(vault)
    group = pages[f"{TIENDA}/Tareas/✅ Tareas de Tienda online"]
    # «Maquetas» la nombra el acta; «Vieja» está cerrada y no la nombra nadie.
    assert f"{TIENDA}/Tareas/✅ Maquetas" in pages
    assert not any(path.endswith("✅ Vieja") for path in pages)
    assert "2 abiertas" in group.body and "Vieja" not in group.body
    assert f"{OTRA}/Intranet/Tareas/✅ Migrar correo" in pages  # en espera: pesa


def test_people_live_in_their_company_team(vault):
    pages = _pages(vault)
    eva = pages[f"{FICTICIA}/Equipo/👤 Eva Ruiz"]
    assert _links(eva.body) == {f"{FICTICIA}/Equipo/👥 Equipo de Ficticia SL"}
    assert "Rol: Diseñadora" in eva.body and "⚠️ Retraso del proveedor: pagos" in eva.body
    assert eva.front["privacyTier"] == "private"
    team = pages[f"{FICTICIA}/Equipo/👥 Equipo de Ficticia SL"]
    assert f"{FICTICIA}/Equipo/👤 Eva Ruiz" in _links(team.body)
    # El propietario es el núcleo: no tiene nota de persona.
    assert not any(path.endswith("Alex Gil") for path in pages)


def test_a_person_in_two_companies_is_a_nexus(vault):
    pages = _pages(vault)
    carmen = pages["entities/Nexos/🔗 Carmen"]
    assert _links(carmen.body) == {
        "entities/Nexos/🕸 Nexos",
        f"{FICTICIA}/Equipo/👥 Equipo de Ficticia SL",
        f"{OTRA}/Equipo/👥 Equipo de Otra SA",
    }
    assert "en Intranet · 1 tarea" in carmen.body  # el motivo de la unión
    assert carmen.front["tags"] == ["persona", "nexo"]
    assert not any(path.endswith("👤 Carmen") for path in pages)
    team = pages[f"{OTRA}/Equipo/👥 Equipo de Otra SA"]
    assert "también con Ficticia SL" in team.body
    assert "entities/Nexos/🔗 Carmen" in _links(pages["entities/Nexos/🕸 Nexos"].body)


def test_people_without_company_are_contacts_and_loose_meetings_go_to_agenda(vault):
    pages = _pages(vault)
    assert "entities/Contactos/👤 Leo" in pages
    meeting = pages["entities/Agenda/📅 2026-03-05 · Café con Leo"]
    assert _links(meeting.body) == {"entities/Agenda/📅 Agenda"}


def test_knowledge_is_a_tree_and_methodologies_are_nexus(vault):
    pages = _pages(vault)
    scrum = pages["concepts/Conocimiento/Metodologías/Scrum/📐 Scrum"]
    assert "- Sprints de dos semanas." in scrum.body
    assert "#### Ceremonias" in scrum.body  # los títulos de MEMORY.md bajan de nivel
    assert "concepts/Conocimiento/Metodologías/Scrum/📄 Guía Scrum" in _links(scrum.body)
    assert f"{TIENDA}/📁 Tienda online" in _links(scrum.body)  # el nexo con el proyecto
    assert "concepts/Conocimiento/Documentación general/📄 Manual de estilo" in pages
    assert f"{TIENDA}/Documentos/📄 Brief tienda" in pages
    knowledge = pages["concepts/Conocimiento/📚 Conocimiento"]
    assert red.DIRECTIVES_NOTE in _links(knowledge.body)


def test_acta_moves_under_its_meeting_with_human_notes(vault):
    snap = _snapshot(vault)
    pages = red.build_pages(snap)
    assert red.write_pages(vault, pages, snap) > 0
    acta = vault / f"{TIENDA}/Reuniones/2026-03-02-kick-off.md"
    assert acta.exists() and not (vault / "sources/proyectos").exists()
    text = acta.read_text()
    assert f"Acta de [[{TIENDA}/Reuniones/📅 2026-03-02 · Kick-off|" in text
    assert text.count(red.START) == 1 and "# Acta: Kick-off Tienda online" in text
    meeting = (vault / f"{TIENDA}/Reuniones/📅 2026-03-02 · Kick-off.md").read_text()
    assert f"[[{TIENDA}/Reuniones/2026-03-02-kick-off|" in meeting
    # La siguiente pasada encuentra el acta ya en su sitio y no la toca.
    snap = _snapshot(vault)
    assert red.write_pages(vault, red.build_pages(snap), snap) == 0


def test_write_keeps_human_notes(vault):
    snap = _snapshot(vault)
    pages = red.build_pages(snap)
    red.write_pages(vault, pages, snap)
    note = vault / f"{TIENDA}/📁 Tienda online.md"
    note.write_text(note.read_text() + "\nMi nota a mano.\n", encoding="utf-8")
    red.write_pages(vault, pages, snap)
    assert note.read_text().endswith("Mi nota a mano.\n")
    index = json.loads((vault / red.TREE_INDEX).read_text())
    assert index["projects"]["Tienda online"]["note"] == f"{TIENDA}/📁 Tienda online"


def test_a_note_that_changes_branch_takes_its_notes_along(vault):
    """Eva pasa a trabajar también con Otra SA: su nota se va a Nexos con lo anotado."""
    snap = _snapshot(vault)
    red.write_pages(vault, red.build_pages(snap), snap)
    red.remember(vault, "Eva Ruiz", "Prefiere correo", datetime.date(2026, 3, 3))
    snap = _snapshot(vault)
    snap.tasks.append(Item("13", "Logo", "Intranet", "Otra SA", "", "Nuevo", ["Eva Ruiz"]))
    red.write_pages(vault, red.build_pages(snap), snap)
    moved = vault / "entities/Nexos/🔗 Eva Ruiz.md"
    assert "- 2026-03-03: Prefiere correo" in moved.read_text()
    assert not (vault / f"{FICTICIA}/Equipo/👤 Eva Ruiz.md").exists()


def test_human_note_with_same_name_is_not_touched(vault):
    snap = _snapshot(vault)
    human = vault / f"{FICTICIA}/🏢 Ficticia SL.md"
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
    assert note == vault / f"{TIENDA}/📁 Tienda online.md"
    text = note.read_text()
    assert text.index(red.END) < text.index("## Notas")
    assert "- 2026-03-03: Prefiere reuniones por la mañana\n- 2026-03-03: Pago con Bizum" in text
    red.write_pages(vault, red.build_pages(snap), snap)  # regenerar no la borra
    assert "Pago con Bizum" in note.read_text()
    assert red.remember(vault, "Carmen", "Le gusta Marvel", day).parent.name == "Nexos"
    with pytest.raises(LookupError, match="Hay:"):
        red.remember(vault, "Otra cosa", "x")


def test_remember_creates_person_or_topic_only_when_asked(vault):
    day = datetime.date(2026, 3, 3)
    with pytest.raises(LookupError, match="new='persona'"):
        red.remember(vault, "Marta", "Le gusta Marvel", day)
    person = red.remember(vault, "Marta", "Le gusta Marvel", day, new="persona")
    assert person == vault / "entities/Contactos/👤 Marta.md"
    topic = red.remember(vault, "Forma de trabajo", "Sprints de dos semanas", day, new="tema")
    assert topic == vault / "concepts/Conocimiento/Temas/💡 Forma de trabajo.md"
    red.remember(vault, "forma de", "Daily de 15 minutos", day)  # ya existe: la encuentra
    assert topic.read_text().count("- 2026-03-03:") == 2
    with pytest.raises(LookupError, match="'persona', 'tema' o 'metodologia'"):
        red.remember(vault, "Otra", "x", day, new="empresa")


def test_a_contact_moves_into_the_company_that_starts_working_with_them(vault):
    """Leo se anotó como contacto; al tener trabajo en Ficticia SL, pasa a su equipo."""
    day = datetime.date(2026, 3, 3)
    red.remember(vault, "Rosa Díaz", "Prefiere llamadas", day, new="persona")
    snap = _snapshot(vault)
    snap.tasks.append(
        Item("14", "Fotos", "Tienda online", "Ficticia SL", "", "Nuevo", ["Rosa Díaz"])
    )
    red.write_pages(vault, red.build_pages(snap), snap)
    text = (vault / f"{FICTICIA}/Equipo/👤 Rosa Díaz.md").read_text()
    assert "generatedBy" in text and "✅ Fotos" in text
    assert text.index(red.END) < text.index("- 2026-03-03: Prefiere llamadas")
    assert not (vault / "entities/Contactos/👤 Rosa Díaz.md").exists()


def test_topics_and_methodologies_written_by_remember_join_the_tree(vault):
    day = datetime.date(2026, 3, 3)
    red.remember(vault, "Kanban", "Límite WIP de 3", day, new="metodologia")
    red.remember(vault, "Viajes", "Hotel cerca de la oficina", day, new="tema")
    snap = _snapshot(vault)
    assert "Kanban" in snap.methods and snap.topics == ["Viajes"]
    red.write_pages(vault, red.build_pages(snap), snap)
    kanban = (vault / "concepts/Conocimiento/Metodologías/Kanban/📐 Kanban.md").read_text()
    assert "Metodología de [[concepts/Conocimiento/Metodologías/🗂 Metodologías|" in kanban
    assert "- 2026-03-03: Límite WIP de 3" in kanban
    assert red.remember(vault, "scrum", "La retro va antes", day).parent.name == "Scrum"


def test_directives_are_mirrored_and_not_rememberable(vault, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert not red.mirror_directives(workspace, vault)  # sin MEMORY.md no hace nada
    (workspace / "MEMORY.md").write_text("# Directivas\n\n- Trabajar con Scrum\n")
    assert red.mirror_directives(workspace, vault)
    assert not red.mirror_directives(workspace, vault)  # sin cambios no reescribe
    text = (vault / f"{red.DIRECTIVES_NOTE}.md").read_text()
    assert "- Trabajar con Scrum" in text and "Rama de [[concepts/Conocimiento/" in text
    with pytest.raises(LookupError):
        red.remember(vault, "Directivas de Jarvis", "x")
    with pytest.raises(LookupError, match="MEMORY.md"):
        red.remember(vault, "Directivas de Jarvis", "x", new="tema")


def test_acta_folder_follows_the_tree_index(vault):
    assert red.acta_folder(vault, "Tienda online", "tienda-online") == (
        vault / "sources/proyectos/tienda-online/actas"
    )
    snap = _snapshot(vault)
    red.write_pages(vault, red.build_pages(snap), snap)
    assert red.acta_folder(vault, "Tienda online", "x") == vault / TIENDA / "Reuniones"
    assert red.acta_file_name("2026-03-02", "Acta: Kick-off") == "📝 2026-03-02 · Kick-off"


def test_note_name_and_document_names_are_readable():
    assert red.note_name('Riesgo: "pagos" #1 / [x]') == "Riesgo pagos 1 x"
    assert red.note_name("a" * 100) == "a" * 80
    pmbok = "input-PMBOK-7Ed---9379f549-d3db-4515-9a44-78b47cb38468.pdf"
    assert red.pretty_document_name(pmbok) == "PMBOK 7Ed"
    snyder = "input-Snyder_A_Project_Manager_s_Book_of_Forms---" + pmbok.split("---", 1)[1]
    assert red.pretty_document_name(snyder) == "Snyder A Project Manager's Book of Forms"
    assert red.pretty_document_name("brief-app-reservas.md") == "Brief app reservas"


def test_same_title_twice_in_a_folder_gets_its_id(vault):
    snap = _snapshot(vault)
    snap.risks.append(Item("15", "Retraso del proveedor: pagos", "Tienda online", "Ficticia SL"))
    pages = {p.path for p in red.build_pages(snap)}
    assert f"{TIENDA}/Riesgos/⚠️ Retraso del proveedor pagos" in pages
    assert f"{TIENDA}/Riesgos/⚠️ Retraso del proveedor pagos (OP-15)" in pages
