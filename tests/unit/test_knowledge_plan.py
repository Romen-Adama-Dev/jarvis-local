from packages.knowledge import plan, red
from packages.knowledge.plan import Link, ProjectPlan, Sprint
from packages.knowledge.red import Item, Snapshot

METHODS = {
    "Scrum": "- Sprints de tres semanas.",
    "PMI": "- Acta de constitución.",
    "Kanban": "- **Límite WIP:** Como máximo 2 tarjetas En curso por persona.",
}


def _item(id_, title, project, company, date="", status="Nuevo", people=(), **plan_fields):
    item = Item(id_, title, project, company, date, status, list(people))
    for key, value in plan_fields.items():
        setattr(item, key, value)
    return item


def _snapshot() -> Snapshot:
    """Un equipo compartido por dos clientes: App (Scrum), Obra (PMI) y Soporte (Kanban)."""
    snap = Snapshot(
        companies={"Taller SL": "", "Clínica SA": ""},
        projects={
            "App": {"company": "Taller SL", "url": "", "gantt": ""},
            "Obra": {"company": "Taller SL", "url": "", "gantt": ""},
            "Soporte": {"company": "Clínica SA", "url": "", "gantt": ""},
        },
        owner="Romen",
        today="2026-10-02",
    )
    story = _item(
        "1",
        "Como cliente quiero reservar",
        "App",
        "Taller SL",
        "2026-10-20",
        people=["Diego"],
        type_name="Historia de usuario",
        sprint="Sprint 2",
        points=5,
    )
    snap.tasks = [
        story,
        _item(
            "2",
            "Conectar calendario",
            "App",
            "Taller SL",
            "2026-10-20",
            people=["Diego"],
            type_name="Tarea",
            parent=story.title,
            sprint="Sprint 2",
            estimate=40,
            spent=2,
        ),
        _item(
            "3",
            "Registro de usuarios",
            "App",
            "Taller SL",
            people=["Diego"],
            type_name="Historia de usuario",
            points=3,
        ),
        _item(
            "4",
            "Horario de verano",
            "Soporte",
            "Clínica SA",
            "2026-10-21",
            people=["Diego"],
            type_name="Tarea",
            spent=1,
        ),
        _item("5", "Regresión", "Soporte", "Clínica SA", status="En curso", people=["Marta"]),
        _item("6", "Accesibilidad", "Soporte", "Clínica SA", status="En curso", people=["Marta"]),
        _item("7", "Textos legales", "Soporte", "Clínica SA", status="En curso", people=["Marta"]),
        _item(
            "8",
            "1. Inicio",
            "Obra",
            "Taller SL",
            "2026-10-09",
            type_name="Tarea de resumen",
            start="2026-10-05",
            people=["Romen"],
        ),
        _item(
            "9",
            "Redactar acta",
            "Obra",
            "Taller SL",
            "2026-09-30",
            people=["Romen"],
            type_name="Tarea",
            parent="1. Inicio",
            estimate=12,
        ),
        _item(
            "10",
            "Alta en la app",
            "Obra",
            "Taller SL",
            "2026-12-30",
            people=["Diego"],
            type_name="Tarea",
            start="2026-12-18",
        ),
    ]
    snap.milestones = [
        _item(
            "20",
            "Salida a producción",
            "App",
            "Taller SL",
            "2026-12-15",
            people=["Romen"],
            type_name="Hito",
        ),
        _item(
            "21",
            "Acta aprobada",
            "Obra",
            "Taller SL",
            "2026-10-09",
            people=["Romen"],
            type_name="Hito",
            parent="1. Inicio",
        ),
    ]
    snap.methods = dict(METHODS)
    snap.project_methods = {"App": ["Scrum"], "Obra": ["PMI"], "Soporte": ["Kanban"]}
    snap.plans = {
        "App": ProjectPlan(
            "en camino",
            "Sprint 1 en marcha.",
            "Scrum",
            ["Presupuesto App"],
            [
                Sprint("Sprint 1", "2026-09-28", "2026-10-16", "en curso"),
                Sprint("Sprint 2", "2026-10-19", "2026-11-06", "en planificación"),
            ],
        ),
        "Obra": ProjectPlan("en riesgo", "La licencia tarda seis semanas.", "PMI"),
    }
    relations = [
        {
            "type": "precedes",
            "description": "La app tiene que estar en producción.",
            "_links": {
                "from": {"href": "/api/v3/work_packages/20", "title": "Salida a producción"},
                "to": {"href": "/api/v3/work_packages/10", "title": "Alta en la app"},
            },
        },
        {
            "type": "blocks",
            "description": None,
            "_links": {
                "from": {"href": "/api/v3/work_packages/9", "title": "Redactar acta"},
                "to": {"href": "/api/v3/work_packages/99", "title": "Fuera del snapshot"},
            },
        },
    ]
    items = {i.id: ("tarea", i) for i in snap.tasks} | {m.id: ("hito", m) for m in snap.milestones}
    plan.attach_relations(relations, items)
    return snap


def test_hours_reads_openproject_durations():
    assert plan.hours("PT40H") == 40
    assert plan.hours("P1DT16H") == 40
    assert plan.hours("PT1H30M") == 1.5
    assert plan.hours(None) == 0
    assert plan.hours("rubbish") == 0


def test_enrich_takes_the_plan_fields_of_a_work_package():
    item = Item("94", "Conectar calendario", "App")
    wp = {
        "startDate": "2026-10-12",
        "storyPoints": None,
        "estimatedTime": "P1DT16H",
        "spentTime": "PT2H",
        "_links": {
            "type": {"title": "Tarea"},
            "parent": {"href": "/api/v3/work_packages/124", "title": "Como taller quiero…"},
            "sprint": {"href": "/api/v3/sprints/2", "title": "Sprint 2"},
            "priority": {"title": "Alta"},
            "category": {"href": None},
        },
    }
    plan.enrich(item, wp)
    assert (item.type_name, item.start, item.parent, item.sprint) == (
        "Tarea",
        "2026-10-12",
        "Como taller quiero…",
        "Sprint 2",
    )
    assert (item.points, item.estimate, item.spent, item.priority, item.category) == (
        0,
        40,
        2,
        "Alta",
        "",
    )


def test_relations_are_read_from_both_ends():
    snap = _snapshot()
    release = snap.milestones[0]
    alta = snap.tasks[-1]
    assert [(lk.verb, lk.title, lk.project, lk.kind) for lk in release.links] == [
        ("precede a", "Alta en la app", "Obra", "tarea")
    ]
    assert [(lk.verb, lk.title, lk.project, lk.kind) for lk in alta.links] == [
        ("sigue a", "Salida a producción", "App", "hito")
    ]
    # El otro extremo puede no estar en el snapshot: se queda su título.
    acta = next(t for t in snap.tasks if t.title == "Redactar acta")
    assert [(lk.verb, lk.title, lk.project) for lk in acta.links] == [
        ("bloquea a", "Fuera del snapshot", "")
    ]


def test_read_plan_takes_status_methodology_budgets_and_sprints():
    class FakeOP:
        def project_budgets(self, project):
            return [{"subject": "Presupuesto App"}]

        def sprints(self, project):
            return [
                {
                    "name": "Sprint 2",
                    "startDate": "2026-10-19",
                    "finishDate": "2026-11-06",
                    "_links": {
                        "status": {"href": "urn:openproject-org:api:v3:sprints:status:in_planning"}
                    },
                },
                {
                    "name": "Sprint 1",
                    "startDate": "2026-09-28",
                    "finishDate": "2026-10-16",
                    "_links": {
                        "status": {"href": "urn:openproject-org:api:v3:sprints:status:active"}
                    },
                },
            ]

    project = {
        "statusExplanation": {"raw": "Sprint 1 en marcha."},
        "_links": {
            "status": {"href": "/api/v3/project_statuses/on_track"},
            "customField1": {"title": "Scrum", "href": "/api/v3/custom_options/2"},
        },
    }
    result = plan.read_plan(FakeOP(), project, {"customField1": "Metodología"})
    assert (result.status, result.status_note, result.methodology) == (
        "en camino",
        "Sprint 1 en marcha.",
        "Scrum",
    )
    assert result.budgets == ["Presupuesto App"]
    assert [(s.name, s.status) for s in result.sprints] == [
        ("Sprint 1", "en curso"),
        ("Sprint 2", "en planificación"),
    ]


def test_same_person_with_deliveries_of_two_projects_in_a_week_is_a_conflict():
    found = [c for c in plan.conflicts(_snapshot()) if c.kind == "semana"]
    assert len(found) == 1
    assert found[0].people == ["Diego"] and found[0].projects == ["App", "Soporte"]
    # La historia hereda la fecha de su tarea: no cuenta dos veces.
    assert "Conectar calendario" in found[0].text and "Como cliente" not in found[0].text


def test_wip_limit_comes_from_the_methodology_rules():
    found = [c for c in plan.conflicts(_snapshot()) if c.kind == "wip"]
    assert [(c.people, c.projects) for c in found] == [(["Marta"], ["Soporte"])]
    assert "3 en curso" in found[0].text and "límite WIP 2" in found[0].text


def test_dependency_between_projects_without_slack_is_a_conflict():
    found = [c for c in plan.conflicts(_snapshot()) if c.kind == "dependencia"]
    assert len(found) == 1
    assert found[0].text.endswith("(Obra, empieza 2026-12-18): solo 3 días de margen")
    assert found[0].projects == ["App", "Obra"]


def test_overdue_work_is_a_conflict_but_summaries_are_not():
    found = [c for c in plan.conflicts(_snapshot()) if c.kind == "vencido"]
    assert [c.text.split("»")[0] for c in found] == ["«Redactar acta"]


def test_project_note_shows_the_plan_of_its_methodology():
    snap = _snapshot()
    app = "\n".join(plan.plan_lines(snap, "App"))
    assert "**en camino** — Sprint 1 en marcha." in app
    assert "Metodología en OpenProject: Scrum" in app
    assert (
        "**Sprint 2** (2026-10-19 → 2026-11-06, en planificación): "
        "1 historia, 5 puntos; 1 tarea, 40 h" in app
    )
    assert "Pila de producto sin sprint:** «Registro de usuarios» (3 pts)" in app
    assert "«Salida a producción» precede a «Alta en la app» (Obra)" in app
    obra = "\n".join(plan.plan_lines(snap, "Obra"))
    assert (
        "## Fases (EDT)" in obra
        and "**1. Inicio** (2026-10-05 → 2026-10-09): 2 paquetes; hitos: Acta aprobada" in obra
    )
    soporte = "\n".join(plan.plan_lines(snap, "Soporte"))
    assert "En curso: 3" in soporte and "Límite WIP: 2" in soporte
    assert "⚠️ Marta tiene 3 en curso" in soporte


def test_person_load_counts_leaf_work_only():
    snap = _snapshot()
    lines = "\n".join(plan.load_lines(snap, "Diego", plan.conflicts(snap)))
    # Conectar (38 h pendientes) + Horario (0) + Alta (0); la historia no suma.
    assert "4 paquetes abiertos en 3 proyectos" in lines
    assert "38 h pendientes · 3 h imputadas" in lines
    assert "2026-10-20 «Conectar calendario» (App)" in lines
    assert "⚠️ Diego, semana del 2026-10-19" in lines


def test_the_tree_carries_plan_load_conflicts_and_dependencies():
    pages = {p.path: p for p in red.build_pages(_snapshot())}
    app = pages["entities/Empresas/Taller SL/App/📁 App"]
    assert "## Sprints" in app.body and "## Dependencias con otros proyectos" in app.body
    assert {
        "targetId": "entity.proyecto.taller-sl.obra",
        "targetTitle": "Obra",
        "kind": "depende-de",
    } in app.front["relationships"]
    diego = pages["entities/Nexos/🔗 Diego"]
    assert "## Carga" in diego.body
    nexos = pages["entities/Nexos/🕸 Nexos"]
    assert "## Conflictos entre empresas" in nexos.body and "Diego, semana" in nexos.body
    release = next(p for path, p in pages.items() if path.endswith("🏁 Salida a producción"))
    assert "## Dependencias" in release.body and "Precede a «Alta en la app» (Obra)" in release.body
    assert {
        "targetId": "entity.tarea.op-10",
        "targetTitle": "Alta en la app",
        "kind": "precede-a",
    } in release.front["relationships"]


def test_link_is_plain_text_in_work_lines():
    item = _item(
        "2",
        "Conectar",
        "App",
        "Taller SL",
        "2026-10-20",
        people=["Diego"],
        sprint="Sprint 2",
        points=0,
        estimate=40,
        spent=2,
    )
    assert red._work_line("tarea", item) == (
        "- ✅ Conectar · vence 2026-10-20 · Nuevo · Sprint 2 · 40 h estimadas / 2 h imputadas"
    )
    assert Link("precede a", "1", "x").kind == ""
