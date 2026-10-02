"""Plan de cada proyecto y carga de cada persona, según OpenProject (docs/OBSIDIAN.md).

`red.py` lee de OpenProject lo justo para el árbol: tareas, hitos, riesgos y reuniones.
Este módulo añade lo que convierte esa lista en un plan:

* cómo se organiza el trabajo según la metodología: sprints, historias y puntos (Scrum),
  fases de la EDT (PMI), columnas y límite WIP del tablero (Kanban);
* cuánto pesa: horas estimadas e imputadas;
* qué depende de qué, también entre proyectos de empresas distintas;
* el estado que el director del proyecto declara en OpenProject.

Cruzándolo todo saca la carga de cada persona y los **conflictos** que Jarvis tiene que
ver sin que se los cuenten: una persona con entregas de dos proyectos la misma semana, un
tablero que supera su límite WIP, una dependencia entre proyectos sin margen o trabajo
vencido. Todo es texto para las notas del vault; no enlaza notas (la regla del árbol).
"""

import datetime
import re
from collections import defaultdict
from dataclasses import dataclass, field

# Estados que no cuentan como trabajo pendiente (los mismos que red.CLOSED).
DONE = ("cerrado", "closed", "rechazado", "rejected")
IN_PROGRESS = ("en curso", "in progress")
SUMMARY_TYPES = ("tarea de resumen", "summary task", "fase")
STORY_TYPES = ("historia de usuario", "user story", "épico", "epic")
# Margen mínimo (días) entre una dependencia de otro proyecto y lo que espera de ella.
MIN_SLACK_DAYS = 7
PROJECT_STATUS = {
    "on_track": "en camino",
    "at_risk": "en riesgo",
    "off_track": "desviado",
    "not_started": "sin empezar",
    "finished": "terminado",
    "discontinued": "interrumpido",
}
SPRINT_STATUS = {"in_planning": "en planificación", "active": "en curso", "completed": "terminado"}
# Relación de OpenProject → (cómo se lee desde el origen, cómo se lee desde el destino).
RELATION_VERBS = {
    "precedes": ("precede a", "sigue a"),
    "follows": ("sigue a", "precede a"),
    "blocks": ("bloquea a", "bloqueado por"),
    "blocked": ("bloqueado por", "bloquea a"),
    "relates": ("relacionado con", "relacionado con"),
    "duplicates": ("duplica a", "duplicado por"),
    "duplicated": ("duplicado por", "duplica a"),
    "includes": ("incluye a", "parte de"),
    "partof": ("parte de", "incluye a"),
    "requires": ("requiere", "requerido por"),
    "required": ("requerido por", "requiere"),
}
# Verbos con orden: el origen tiene que acabar antes de que empiece el destino.
ORDERING = {"precede a", "bloquea a"}
_DURATION = re.compile(
    r"^P(?:(?P<d>\d+(?:\.\d+)?)D)?(?:T(?:(?P<h>\d+(?:\.\d+)?)H)?(?:(?P<m>\d+)M)?)?$"
)
_WIP = re.compile(r"WIP\D{0,40}?(\d+)", re.IGNORECASE)


@dataclass
class Link:
    """Dependencia de un paquete de trabajo con otro, leída desde el primero."""

    verb: str  # "precede a", "bloqueado por"…
    item_id: str
    title: str
    project: str = ""
    kind: str = ""  # tarea, hito o riesgo (para el id de la relación en el frontmatter)
    note: str = ""


@dataclass
class Sprint:
    name: str
    start: str = ""
    finish: str = ""
    status: str = ""


@dataclass
class ProjectPlan:
    status: str = ""  # en camino, en riesgo…
    status_note: str = ""
    methodology: str = ""  # campo "Metodología" del proyecto en OpenProject
    budgets: list[str] = field(default_factory=list)
    sprints: list[Sprint] = field(default_factory=list)


@dataclass
class Conflict:
    kind: str  # semana, wip, dependencia, vencido
    text: str
    people: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)


# --- Lectura de OpenProject ----------------------------------------------------------------


def hours(duration: str | None) -> float:
    """Horas de una duración ISO 8601 de OpenProject ("PT40H", "P1DT16H" = 40 h)."""
    match = _DURATION.match(duration or "")
    if not match:
        return 0.0
    days, hrs, mins = (float(match[g] or 0) for g in ("d", "h", "m"))
    return days * 24 + hrs + mins / 60


def _title(links: dict, key: str) -> str:
    return (links.get(key) or {}).get("title") or ""


def enrich(item, wp: dict) -> None:
    """Completa un red.Item con lo que el paquete de trabajo sabe del plan."""
    links = wp["_links"]
    item.type_name = _title(links, "type")
    item.start = wp.get("startDate") or ""
    item.parent = _title(links, "parent")
    item.sprint = _title(links, "sprint")
    item.points = wp.get("storyPoints") or 0
    item.estimate = hours(wp.get("estimatedTime"))
    item.spent = hours(wp.get("spentTime"))
    item.priority = _title(links, "priority")
    item.category = _title(links, "category")


def _project_custom_fields(op) -> dict[str, str]:
    """customFieldN → nombre, de los campos de proyecto."""
    schema = op.project_schema()
    return {k: v.get("name", "") for k, v in schema.items() if k.startswith("customField")}


def read_plan(op, project: dict, field_names: dict[str, str] | None = None) -> ProjectPlan:
    """Estado, metodología declarada, presupuestos y sprints de un proyecto."""
    links = project["_links"]
    status = ((links.get("status") or {}).get("href") or "").rsplit("/", 1)[-1]
    plan = ProjectPlan(
        status=PROJECT_STATUS.get(status, ""),
        status_note=((project.get("statusExplanation") or {}).get("raw") or "").strip(),
    )
    for key, name in (field_names or {}).items():
        if name.lower().startswith("metodolog") and _title(links, key):
            plan.methodology = _title(links, key)
    plan.budgets = [b["subject"] for b in op.project_budgets(project)]
    for sprint in op.sprints(project):
        state = (sprint["_links"].get("status") or {}).get("href", "").rsplit(":", 1)[-1]
        plan.sprints.append(
            Sprint(
                sprint["name"],
                sprint.get("startDate") or "",
                sprint.get("finishDate") or "",
                SPRINT_STATUS.get(state, ""),
            )
        )
    plan.sprints.sort(key=lambda s: (s.start or "9999", s.name))
    return plan


def attach_relations(relations: list[dict], items: dict[str, tuple[str, object]]) -> None:
    """Añade a cada paquete sus dependencias (`items`: id → (tipo de nota, red.Item))."""
    for relation in relations:
        verbs = RELATION_VERBS.get(relation.get("type", ""))
        if not verbs:
            continue
        ends = [
            (
                relation["_links"][k]["href"].rsplit("/", 1)[-1],
                relation["_links"][k].get("title", ""),
            )
            for k in ("from", "to")
        ]
        note = str(relation.get("description") or "").strip()
        for ((me, _), (other, other_title)), verb in zip((ends, ends[::-1]), verbs, strict=True):
            if me not in items:
                continue
            kind, target = items.get(other, ("", None))
            items[me][1].links.append(
                Link(
                    verb,
                    other,
                    target.title if target else other_title,
                    target.project if target else "",
                    kind,
                    note,
                )
            )


def read_all(op, snap, by_project: dict[str, dict]) -> None:
    """Plan de cada proyecto y dependencias de todos los paquetes del snapshot."""
    names = _project_custom_fields(op)
    for name, project in by_project.items():
        snap.plans[name] = read_plan(op, project, names)
    items = {}
    for kind, group in (("tarea", snap.tasks), ("hito", snap.milestones), ("riesgo", snap.risks)):
        items.update({i.id: (kind, i) for i in group})
    attach_relations(op.relations(), items)


# --- Análisis ------------------------------------------------------------------------------


def is_open(item) -> bool:
    return not any(mark in item.status.lower() for mark in DONE)


def _date(text: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(text[:10]) if text else None
    except ValueError:
        return None


def _week_label(day: datetime.date) -> str:
    monday = day - datetime.timedelta(days=day.weekday())
    return f"semana del {monday.isoformat()}"


def wip_limits(snap) -> dict[str, int]:
    """Proyecto → límite WIP por persona, si su metodología lo fija en MEMORY.md."""
    limits = {}
    for project, methods in snap.project_methods.items():
        for method in methods:
            if match := _WIP.search(snap.methods.get(method, "")):
                limits[project] = int(match[1])
    return limits


def work_items(snap) -> list[tuple[str, object]]:
    """Paquetes con responsable que forman el plan: tareas e hitos (no riesgos)."""
    return [("tarea", t) for t in snap.tasks] + [("hito", m) for m in snap.milestones]


def _containers(snap) -> set[tuple[str, str]]:
    """(proyecto, título) de los paquetes con hijas: fases, épicos, historias con tareas."""
    items = [i for _, i in work_items(snap)] + list(snap.risks)
    return {(i.project, i.parent) for i in items if i.parent}


def leaf_work(snap) -> list[tuple[str, object]]:
    """Paquetes que son trabajo en sí: sin hijas (sus fechas y horas no son derivadas)."""
    parents = _containers(snap)
    return [
        (kind, i)
        for kind, i in work_items(snap)
        if not _is_summary(i) and (i.project, i.title) not in parents
    ]


def conflicts(snap) -> list[Conflict]:
    today = _date(snap.today) or datetime.date.today()
    return (
        _same_week(snap, today)
        + _over_wip(snap)
        + _tight_dependencies(snap)
        + _overdue(snap, today)
    )


def _same_week(snap, today: datetime.date) -> list[Conflict]:
    """La misma persona con entregas de varios proyectos la misma semana."""
    weeks: dict[tuple[str, str], list] = defaultdict(list)
    for kind, item in leaf_work(snap):
        due = _date(item.date)
        if kind != "tarea" or not due or due < today or not is_open(item):
            continue
        for person in item.people:
            weeks[(person, _week_label(due))].append(item)
    found = []
    for (person, week), items in sorted(weeks.items()):
        projects = sorted({i.project for i in items})
        if len(projects) >= 2:
            what = "; ".join(f"«{i.title}» ({i.project}, {i.date})" for i in items)
            found.append(Conflict("semana", f"{person}, {week}: {what}", [person], projects))
    return found


def _over_wip(snap) -> list[Conflict]:
    """Más trabajo en curso del que permite el tablero."""
    found = []
    for project, limit in sorted(wip_limits(snap).items()):
        doing: dict[str, list] = defaultdict(list)
        for item in snap.tasks:
            if item.project == project and item.status.lower() in IN_PROGRESS:
                for person in item.people:
                    doing[person].append(item)
        for person, items in sorted(doing.items()):
            if len(items) > limit:
                names = ", ".join(f"«{i.title}»" for i in items)
                text = f"{person} tiene {len(items)} en curso en {project} (límite WIP {limit}): "
                found.append(Conflict("wip", text + names, [person], [project]))
    return found


def _tight_dependencies(snap) -> list[Conflict]:
    """Dependencias entre proyectos con menos de MIN_SLACK_DAYS días de margen."""
    by_id = {i.id: i for _, i in work_items(snap)}
    found = []
    for _, item in work_items(snap):
        for link in item.links:
            if link.verb not in ORDERING or not link.project or link.project == item.project:
                continue
            after = by_id.get(link.item_id)
            end = _date(item.date)
            begin = _date(after.start or after.date) if after else None
            if not end or not begin or not is_open(item):
                continue
            slack = (begin - end).days
            if slack >= MIN_SLACK_DAYS:
                continue
            state = "sin margen" if slack <= 0 else f"solo {slack} días de margen"
            text = (
                f"«{item.title}» ({item.project}, {item.date}) {link.verb} «{after.title}» "
                f"({after.project}, empieza {begin.isoformat()}): {state}"
            )
            people = sorted(set(item.people + after.people))
            found.append(
                Conflict("dependencia", text, people, sorted({item.project, after.project}))
            )
    return found


def _overdue(snap, today: datetime.date) -> list[Conflict]:
    found = []
    for _, item in leaf_work(snap):
        due = _date(item.date)
        if due and due < today and is_open(item):
            text = f"«{item.title}» ({item.project}) venció el {item.date} · {item.status}"
            found.append(Conflict("vencido", text, list(item.people), [item.project]))
    return found


def _is_summary(item) -> bool:
    return item.type_name.lower() in SUMMARY_TYPES


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# --- Texto para las notas ------------------------------------------------------------------


def _h(value: float) -> str:
    return f"{value:g} h"


def item_extra(item) -> str:
    """Lo que añade el plan a la línea de un paquete: sprint, puntos y horas."""
    parts = []
    if item.sprint:
        parts.append(item.sprint)
    if item.points:
        parts.append(f"{item.points:g} pts")
    if item.estimate or item.spent:
        parts.append(
            " / ".join(
                x
                for x in (
                    f"{_h(item.estimate)} estimadas" if item.estimate else "",
                    f"{_h(item.spent)} imputadas" if item.spent else "",
                )
                if x
            )
        )
    return " · ".join(parts)


def item_facts(item) -> list[tuple[str, str]]:
    """Datos del plan para la nota de un paquete (hito, riesgo o tarea que pesa)."""
    return [
        (
            "Tipo",
            item.type_name if item.type_name.lower() not in ("tarea", "hito", "riesgo") else "",
        ),
        ("Dentro de", item.parent),
        ("Sprint", item.sprint),
        ("Puntos", f"{item.points:g}" if item.points else ""),
        ("Horas", item_extra_hours(item)),
        ("Prioridad", item.priority if item.priority.lower() not in ("", "normal") else ""),
        ("Categoría", item.category),
    ]


def item_extra_hours(item) -> str:
    if not (item.estimate or item.spent):
        return ""
    return f"{_h(item.estimate)} estimadas · {_h(item.spent)} imputadas"


def link_lines(item) -> list[str]:
    if not item.links:
        return []
    lines = ["", "## Dependencias"]
    for link in item.links:
        where = f" ({link.project})" if link.project and link.project != item.project else ""
        lines.append(
            f"- {link.verb.capitalize()} «{link.title}»{where}"
            + (f" — {link.note}" if link.note else "")
        )
    return lines


def related_projects(snap, project: str) -> list[str]:
    """Otros proyectos de los que depende (o que dependen de) este, por sus paquetes."""
    items = [i for _, i in work_items(snap)] + list(snap.risks)
    others = {
        link.project
        for item in items
        if item.project == project
        for link in item.links
        if link.project and link.project != project and link.project in snap.projects
    }
    return sorted(others)


def plan_lines(snap, project: str, found: list[Conflict] | None = None) -> list[str]:
    """Secciones del plan para la nota de un proyecto."""
    plan = snap.plans.get(project)
    tasks = [t for t in snap.tasks if t.project == project]
    work = [i for _, i in work_items(snap) if i.project == project]
    leaves = [i for _, i in leaf_work(snap) if i.project == project]
    lines: list[str] = []
    if plan and (plan.status or plan.status_note):
        lines += [
            "",
            "## Estado",
            f"- **{plan.status or 'sin estado'}**"
            + (f" — {plan.status_note}" if plan.status_note else ""),
        ]
    estimate, spent = sum(i.estimate for i in leaves), sum(i.spent for i in leaves)
    facts = []
    if plan and plan.methodology:
        facts.append(f"Metodología en OpenProject: {plan.methodology}")
    if estimate or spent:
        facts.append(f"Horas: {_h(estimate)} estimadas · {_h(spent)} imputadas")
    if plan and plan.budgets:
        facts.append("Presupuesto: " + ", ".join(plan.budgets))
    lines += ["", "## Plan", *(f"- {f}" for f in facts)] if facts else []
    lines += (
        _sprint_lines(plan, tasks) + _phase_lines(tasks, work) + _board_lines(snap, project, tasks)
    )
    lines += _external_lines(work + [r for r in snap.risks if r.project == project], project)
    alerts = [c for c in (conflicts(snap) if found is None else found) if project in c.projects]
    if alerts:
        lines += ["", "## Alertas", *(f"- ⚠️ {c.text}" for c in alerts)]
    return lines


def _sprint_lines(plan: ProjectPlan | None, tasks: list) -> list[str]:
    if not plan or not plan.sprints:
        return []
    lines = ["", "## Sprints"]
    for sprint in plan.sprints:
        mine = [t for t in tasks if t.sprint == sprint.name]
        stories = [t for t in mine if t.type_name.lower() in STORY_TYPES]
        points = sum(t.points for t in stories)
        when = " → ".join(x for x in (sprint.start, sprint.finish) if x)
        head = f"- **{sprint.name}**" + (
            f" ({when}, {sprint.status})" if when or sprint.status else ""
        )
        body = []
        if stories:
            body.append(f"{_count(len(stories), 'historia', 'historias')}, {points:g} puntos")
        if others := [t for t in mine if t not in stories]:
            body.append(
                f"{_count(len(others), 'tarea', 'tareas')}, {_h(sum(t.estimate for t in others))}"
            )
        lines.append(head + (": " + "; ".join(body) if body else ""))
    backlog = [
        t for t in tasks if t.type_name.lower() in STORY_TYPES[:2] and not t.sprint and is_open(t)
    ]
    if backlog:
        lines.append(
            "- **Pila de producto sin sprint:** "
            + ", ".join(f"«{t.title}» ({t.points:g} pts)" for t in backlog)
        )
    return lines


def _phase_lines(tasks: list, work: list) -> list[str]:
    phases = sorted((t for t in tasks if _is_summary(t)), key=lambda t: (t.start or "", t.title))
    if not phases:
        return []
    lines = ["", "## Fases (EDT)"]
    for phase in phases:
        children = [i for i in work if i.parent == phase.title]
        when = " → ".join(x for x in (phase.start, phase.date) if x)
        milestones = [i.title for i in children if i.type_name.lower() in ("hito", "milestone")]
        lines.append(
            f"- **{phase.title}**"
            + (f" ({when})" if when else "")
            + f": {len(children)} paquetes"
            + (f"; hitos: {', '.join(milestones)}" if milestones else "")
        )
    return lines


def _board_lines(snap, project: str, tasks: list) -> list[str]:
    limit = wip_limits(snap).get(project)
    if limit is None:
        return []
    counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        counts[task.status or "Sin estado"] += 1
    columns = " · ".join(f"{status}: {n}" for status, n in counts.items())
    return ["", "## Tablero", f"- {columns}", f"- Límite WIP: {limit} en curso por persona"]


def _external_lines(items: list, project: str) -> list[str]:
    lines = []
    for item in items:
        for link in item.links:
            if link.project and link.project != project:
                lines.append(
                    f"- «{item.title}» {link.verb} «{link.title}» ({link.project})"
                    + (f" — {link.note}" if link.note else "")
                )
    return (["", "## Dependencias con otros proyectos", *lines]) if lines else []


def load_lines(snap, person: str, found: list[Conflict]) -> list[str]:
    """Sección «Carga» de la nota de una persona."""
    today = _date(snap.today) or datetime.date.today()
    mine = [(k, i) for k, i in leaf_work(snap) if person in i.people]
    open_items = [(k, i) for k, i in mine if is_open(i)]
    if not mine:
        return []
    pending = sum(max(i.estimate - i.spent, 0) for _, i in open_items)
    spent = sum(i.spent for _, i in mine)
    projects = sorted({i.project for _, i in open_items if i.project})
    lines = [
        "",
        "## Carga",
        f"- {len(open_items)} paquetes abiertos en {len(projects)} proyectos"
        + (f" ({', '.join(projects)})" if projects else "")
        + f" · {_h(pending)} pendientes · {_h(spent)} imputadas",
    ]
    soon = sorted(
        (
            i
            for _, i in open_items
            if (d := _date(i.date)) and today <= d <= today + datetime.timedelta(days=21)
        ),
        key=lambda i: i.date,
    )
    if soon:
        lines.append(
            "- Próximas entregas (21 días): "
            + "; ".join(f"{i.date} «{i.title}» ({i.project})" for i in soon[:6])
        )
    mine_conflicts = [c for c in found if person in c.people]
    lines += [f"- ⚠️ {c.text}" for c in mine_conflicts]
    return lines


def conflict_lines(found: list[Conflict], shared: set[str]) -> list[str]:
    """Conflictos que tocan a personas compartidas entre empresas (para la rama Nexos)."""
    mine = [c for c in found if set(c.people) & shared or (c.kind == "dependencia")]
    if not mine:
        return []
    return ["", "## Conflictos entre empresas", *(f"- ⚠️ {c.text}" for c in mine)]
