"""Red de conocimiento en el vault de Obsidian (docs/OBSIDIAN.md).

Convierte lo que Jarvis ya sabe de cada proyecto en notas enlazadas, para que Obsidian las
muestre y el wiki de OpenClaw (memory-wiki) las use como memoria estructurada
(`pageType: entity`, `relationships`). Son dos capas con reglas distintas:

* **Árbol** (contención: cada nota tiene un padre y solo uno), y la carpeta es el árbol:

      entities/empresas/<Empresa>.md
      entities/empresas/<Empresa>/<Proyecto>.md
      entities/empresas/<Empresa>/<Proyecto>/{hitos,riesgos,reuniones,tareas}/<Nota>.md

  El enlace estructural lo declara siempre el hijo (`relationships: pertenece-a`); el
  padre lista a sus hijos para poder navegarlos, pero no repite la relación.
  Las tareas solo son nota propia cuando pesan (bloqueadas o nombradas en un acta); el
  resto se quedan como líneas de la nota del proyecto para no ahogar el árbol.

* **Red** (asociación, muchos a muchos): personas, documentos del RAG, actas y conceptos.
  Aquí sí se cruzan proyectos y empresas: una persona enlaza con todo en lo que participa.

Los conceptos (Gestión de riesgos, Hitos y cronograma...) son índices por proyecto: no
enlazan cada riesgo de cada empresa, que es lo que convertía el grafo en una maraña.
La nota raíz es `Red de conocimiento`.

Todo es local: lee OpenProject y la API de Jarvis y escribe Markdown en el vault. Cada nota
generada tiene un bloque gestionado entre marcas; lo que escribas fuera de él se conserva.
No borra nada: si algo desaparece de OpenProject, su nota se queda (se puede borrar a mano).

    python -m packages.knowledge.red --vault DIR            # una pasada
    python -m packages.knowledge.red --vault DIR --every 600
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

START = "<!-- jarvis:red:start -->"
END = "<!-- jarvis:red:end -->"
ROOT_NOTE = "Red de conocimiento"
# Proyecto de OpenProject con las reuniones sin proyecto (CALENDAR_PROVIDER=openproject).
AGENDA = os.environ.get("OPENPROJECT_CALENDAR_PROJECT", "Agenda")

# Conceptos que agrupan nodos del mismo tipo (dan estructura al grafo).
HUBS = {
    "riesgos": (
        "Gestión de riesgos",
        "Riesgos de los proyectos, con probabilidad, impacto, mitigación y responsable.",
    ),
    "hitos": ("Hitos y cronograma", "Hitos de los proyectos: fechas clave del cronograma."),
    "reuniones": ("Reuniones y actas", "Reuniones de los proyectos y sus actas."),
    "documentos": ("Documentación", "Documentos del RAG de Jarvis, por empresa y proyecto."),
    "equipo": ("Equipo", "Personas que participan en los proyectos."),
}
CLOSED = ("cerrado", "closed", "rechazado", "rejected")
MEETING_STATES = {
    "draft": "borrador",
    "open": "convocada",
    "in_progress": "en curso",
    "closed": "celebrada",
}


# --- Modelo ------------------------------------------------------------------------------


@dataclass
class Item:
    """Hito, riesgo, tarea, reunión o documento."""

    id: str
    title: str
    project: str = ""
    company: str = ""
    date: str = ""
    status: str = ""
    people: list[str] = field(default_factory=list)
    detail: str = ""
    url: str = ""
    # Solo en las actas: títulos de las tareas que nombra (deciden qué tarea es nota).
    mentions: list[str] = field(default_factory=list)


@dataclass
class Snapshot:
    companies: dict[str, str] = field(default_factory=dict)  # empresa -> url
    projects: dict[str, dict] = field(default_factory=dict)  # proyecto -> {company, url, ...}
    milestones: list[Item] = field(default_factory=list)
    risks: list[Item] = field(default_factory=list)
    tasks: list[Item] = field(default_factory=list)
    meetings: list[Item] = field(default_factory=list)
    documents: list[Item] = field(default_factory=list)
    actas: list[Item] = field(default_factory=list)  # id = ruta relativa en el vault
    roles: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


# --- Utilidades --------------------------------------------------------------------------


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def note_name(text: str, limit: int = 80) -> str:
    """Nombre de archivo válido y legible (es la etiqueta del nodo en el grafo)."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", text)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:limit].rstrip(" .") or "sin título"


def link(name: str, alias: str = "") -> str:
    note = note_name(name)
    return f"[[{note}|{alias}]]" if alias and alias != note else f"[[{note}]]"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _key(text)).strip("-") or "x"


def _frontmatter(data: dict) -> str:
    # JSON es YAML válido: sin dependencias y sin problemas de comillas.
    lines = ["---"]
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def split_people(text: str) -> list[str]:
    """«Eva Gil (Diseñadora), Leo» -> ["Eva Gil (Diseñadora)", "Leo"]."""
    people = []
    for chunk in re.split(r",\s*(?![^()]*\))", text or ""):
        chunk = chunk.strip()
        if not chunk or chunk in ("—", "-", "?"):
            continue
        people.append(chunk)
    return people


def _titles(links: list[dict]) -> list[str]:
    return [x.get("title", "") for x in links]


def person_and_role(chunk: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\((.*)\)\s*$", chunk)
    return (match.group(1).strip(), match.group(2).strip()) if match else (chunk.strip(), "")


# --- Lectura de datos --------------------------------------------------------------------


_ACTA_FIELD = re.compile(r"^- \*\*(?P<k>[^*]+):\*\*\s*(?P<v>.*)$", re.MULTILINE)


def _table_column(markdown: str, header: str) -> list[str]:
    """Valores de la columna `header` de las tablas Markdown (acciones, riesgos)."""
    values, column = [], None
    for line in markdown.splitlines():
        if not line.startswith("|"):
            column = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if column is None:
            keys = [_key(c) for c in cells]
            column = keys.index(header) if header in keys else -1
        elif column >= 0 and column < len(cells) and not set(cells[column]) <= set("-: "):
            if cells[column] not in ("—", "?"):
                values.append(cells[column])
    return values


def read_actas(vault: Path) -> list[Item]:
    """Actas guardadas por Jarvis (sources/proyectos/<proyecto>/actas/*.md)."""
    actas = []
    for path in sorted(vault.glob("sources/proyectos/*/actas/*.md")):
        text = path.read_text(encoding="utf-8")
        fields = {m["k"].strip().lower(): m["v"].strip() for m in _ACTA_FIELD.finditer(text)}
        title = re.search(r"^title:\s*\"?(.*?)\"?\s*$", text, re.MULTILINE)
        people = [person_and_role(c) for c in split_people(fields.get("asistentes", ""))]
        people += [(who, "") for who in _table_column(text, "responsable")]
        actas.append(
            Item(
                id=path.relative_to(vault).with_suffix("").as_posix(),
                title=title.group(1) if title else path.stem,
                project=fields.get("proyecto", ""),
                date=fields.get("fecha", ""),
                people=[p for p, _ in people],
                # Rol de cada persona (el de la lista de asistentes; vacío si no lo dice).
                detail=json.dumps(
                    {p: r for p, r in reversed(people) if r or p not in dict(people)},
                    ensure_ascii=False,
                ),
                mentions=_table_column(text, "tarea"),
            )
        )
    return actas


def collect(op, documents: list[dict], vault: Path, owner_name: str = "") -> Snapshot:
    """Reúne lo que hay en OpenProject, el RAG y las actas del vault."""
    snap = Snapshot()
    by_id: dict[int, dict] = {}
    for project in op.projects() if op else []:
        by_id[project["id"]] = project
    for project in by_id.values():
        parent = (project["_links"].get("parent") or {}).get("href")
        parent_id = int(parent.rsplit("/", 1)[-1]) if parent else None
        if parent_id and parent_id in by_id:
            company = by_id[parent_id]["name"]
            snap.projects[project["name"]] = {
                "company": company,
                "url": op.project_url(project),
                "gantt": op.project_url(project, "gantt"),
            }
        elif not parent_id and project["name"] != AGENDA:
            snap.companies[project["name"]] = op.project_url(project)

    def who(title: str) -> str:
        if not title or _key(title).startswith("jarvis"):
            return ""
        if _key(title) in ("administrador admin", "admin") or title == os.environ.get(
            "OPENPROJECT_OWNER_TITLE", "Administrador Admin"
        ):
            return owner_name
        return title

    for project in [p for p in by_id.values() if p["name"] in snap.projects]:
        info = snap.projects[project["name"]]
        for wp in op.work_packages(project, only_open=False, limit=200):
            links = wp["_links"]
            kind = _key(links["type"]["title"])
            description = ((wp.get("description") or {}).get("raw") or "").strip()
            people = [p for p in [who((links.get("assignee") or {}).get("title", ""))] if p]
            named = re.search(r"Responsable:\s*(.+)", description)
            if named and not people:
                people.append(named.group(1).strip())
            item = Item(
                id=str(wp["id"]),
                title=wp["subject"],
                project=project["name"],
                company=info["company"],
                date=wp.get("dueDate") or wp.get("date") or "",
                status=links["status"]["title"],
                people=people,
                detail=description.split("\nOrigen:")[0].strip()[:400],
                url=op.work_package_url(wp),
            )
            if kind in ("hito", "milestone"):
                snap.milestones.append(item)
            elif kind in ("riesgo", "risk"):
                snap.risks.append(item)
            else:
                snap.tasks.append(item)
    if op:
        now = datetime.datetime.now(datetime.UTC)
        span = datetime.timedelta(days=365)
        for meeting in op.meetings(now - span, now + span):
            links = meeting["_links"]
            project_name = links["project"]["title"]
            snap.meetings.append(
                Item(
                    id=str(meeting["id"]),
                    title=meeting["title"],
                    project="" if project_name == AGENDA else project_name,
                    company=snap.projects.get(links["project"]["title"], {}).get("company", ""),
                    date=meeting["startTime"][:10],
                    status=MEETING_STATES.get(meeting.get("state", ""), ""),
                    people=[p for p in map(who, _titles(links.get("participants", []))) if p],
                    url=op.meeting_url(meeting),
                )
            )  # fmt: skip
    for doc in documents:
        meta = doc.get("doc_metadata") or {}
        name = re.sub(r"(---[0-9a-f-]{36})?\.[a-z0-9]+$", "", doc["filename"])
        name = name.removeprefix("input-")
        snap.documents.append(
            Item(
                id=doc["id"],
                title=name,
                project=meta.get("project", ""),
                company=meta.get("company", ""),
                date=str(doc.get("created_at", ""))[:10],
                status=doc.get("status", ""),
            )
        )
    # Empresas y proyectos que solo tienen documentos (sin proyecto en OpenProject).
    for doc in snap.documents:
        if doc.company and doc.company not in snap.companies:
            snap.companies[doc.company] = ""
        if doc.project and doc.project not in snap.projects:
            snap.projects[doc.project] = {"company": doc.company, "url": "", "gantt": ""}
    snap.actas = read_actas(vault)
    # Las actas indexadas en el RAG ya son notas del vault: sin nodo de documento aparte.
    acta_names = {a.id.rsplit("/", 1)[-1] for a in snap.actas}
    snap.documents = [d for d in snap.documents if d.title not in acta_names]
    for acta in snap.actas:
        for person, role in json.loads(acta.detail or "{}").items():
            if role:
                snap.roles[person].add(role)
    if owner_name:
        _merge_owner(snap, owner_name)
    return snap


def _near(a: str, b: str) -> bool:
    """Distancia de edición <= 1 (errores de transcripción: «Alexx» por «Alex»)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :] or (len(a) == len(b) and a[i + 1 :] == b[i + 1 :])


def _merge_owner(snap: Snapshot, owner: str) -> None:
    """El propietario aparece con variantes en las actas: se unifican en su nombre. Solo
    para él, que sale en casi todo; con el resto el riesgo de unir a dos personas es mayor."""
    target = _key(owner)
    first = target.split(" ")[0]

    def fix(name: str) -> str:
        key = _key(name)
        return owner if len(key) >= 4 and (_near(key, target) or _near(key, first)) else name

    for item in [*snap.tasks, *snap.milestones, *snap.risks, *snap.meetings, *snap.actas]:
        item.people = list(dict.fromkeys(fix(p) for p in item.people))
    for name in list(snap.roles):
        if fix(name) != name:
            snap.roles[owner] |= snap.roles.pop(name)


# --- Notas -------------------------------------------------------------------------------


@dataclass
class Page:
    path: str  # relativa al vault, sin .md
    front: dict
    body: str


def _entity(kind: str, name: str, tags: list[str], relationships: list[dict], **extra) -> dict:
    return {
        "pageType": "entity",
        "entityType": kind,
        "id": f"entity.{kind}.{_slug(name)}",
        "title": name,
        "tags": tags,
        "relationships": relationships,
        **extra,
    }


def _rel(kind: str, target_kind: str, name: str) -> dict:
    return {"targetId": f"entity.{target_kind}.{_slug(name)}", "targetTitle": name, "kind": kind}


def _item_line(item: Item, with_project: bool = False) -> str:
    parts = [link(_item_note(item), item.title)]
    if item.date:
        parts.append(item.date)
    if item.status:
        parts.append(item.status)
    if with_project and item.project:
        parts.append(link(item.project))
    return "- " + " · ".join(parts)


def _item_note(item: Item) -> str:
    # Las actas ya son notas del vault (id = ruta): se enlazan por su nombre de archivo.
    if "/" in item.id:
        return item.id.rsplit("/", 1)[-1]
    if item.id.isdigit():  # paquete de trabajo o reunión de OpenProject
        return f"{note_name(item.title, 68)} (OP-{item.id})"
    return note_name(item.title)


def _company_dir(company: str) -> str:
    return f"entities/empresas/{note_name(company)}"


def _project_path(company: str, project: str) -> str:
    """La nota del proyecto vive dentro de la carpeta de su empresa: la carpeta es el árbol."""
    return f"{_company_dir(company)}/{note_name(project)}"


# Estados en los que una tarea deja de ser una línea y merece su propia nota.
BLOCKED = ("bloquead", "blocked", "en espera", "on hold", "detenid", "parad")


def _task_is_node(task: Item, acta_tasks: set[str]) -> bool:
    """Una tarea pesa —y entra en el árbol— si está bloqueada o si la nombra un acta."""
    if any(mark in _key(task.status) for mark in BLOCKED):
        return True
    return _key(task.title) in acta_tasks


def _task_line(task: Item, with_project: bool = False, as_node: bool = False) -> str:
    title = link(_item_note(task), task.title) if as_node else task.title
    parts = [f"[#{task.id}]({task.url}) {title}" if task.url else title]
    if task.date:
        parts.append(f"vence {task.date}")
    if task.status:
        parts.append(task.status)
    if with_project and task.project:
        parts.append(link(task.project))
    elif task.people:
        parts.append(link(task.people[0]))
    return "- " + " · ".join(parts)


def build_pages(snap: Snapshot) -> list[Page]:
    """Todas las notas de la red a partir de una instantánea (función pura)."""
    pages: list[Page] = []
    project_people: dict[str, set[str]] = defaultdict(set)
    person_items: dict[str, list[tuple[str, Item]]] = defaultdict(list)

    for kind, items in (
        ("tarea", snap.tasks),
        ("hito", snap.milestones),
        ("riesgo", snap.risks),
        ("reunion", snap.meetings),
        ("acta", snap.actas),
    ):
        for item in items:
            item.people = list(dict.fromkeys(item.people))
            for person in item.people:
                project_people[item.project].add(person)
                person_items[person].append((kind, item))

    acta_tasks = {_key(t) for acta in snap.actas for t in acta.mentions}
    task_nodes = {id(t) for t in snap.tasks if _task_is_node(t, acta_tasks)}

    def by_project(items: list[Item], project: str) -> list[Item]:
        return sorted((i for i in items if i.project == project), key=lambda i: i.date or "9")

    def company_of(project: str) -> str:
        return snap.projects.get(project, {}).get("company", "")

    # Empresas (raíz del árbol). No declara «tiene-proyecto»: la relación la pone el hijo.
    for company, url in sorted(snap.companies.items()):
        projects = sorted(p for p, info in snap.projects.items() if info["company"] == company)
        docs = [d for d in snap.documents if d.company == company and not d.project]
        people = sorted({p for proj in projects for p in project_people[proj]})
        body = [
            f"# {company}",
            "",
            f"Empresa en [[{ROOT_NOTE}]]" + (f" · [OpenProject]({url})" if url else ""),
            "",
            "## Proyectos",
            *([f"- {link(p)}" for p in projects] or ["- Ninguno todavía."]),
        ]
        if people:
            body += ["", "## Personas", *(f"- {link(p)}" for p in people)]
        if docs:
            body += ["", "## Documentación de la empresa", *(_item_line(d) for d in docs)]
        pages.append(
            Page(
                _company_dir(company),
                _entity("empresa", company, ["empresa"], []),
                "\n".join(body),
            )
        )

    # Proyectos (hijos de su empresa)
    for project, info in sorted(snap.projects.items()):
        company = info["company"]
        open_tasks = [t for t in by_project(snap.tasks, project) if _key(t.status) not in CLOSED]
        header = f"Proyecto de {link(company)}"
        if info["url"]:
            header += f" · [OpenProject]({info['url']}) · [Gantt]({info['gantt']})"
        sections = [f"# {project}", "", header]
        people = sorted(project_people[project])
        if people:
            roles = {p: ", ".join(sorted(snap.roles.get(p, []))) for p in people}
            sections += ["", "## Equipo"]
            sections += [f"- {link(p)}" + (f" — {roles[p]}" if roles[p] else "") for p in people]
        for title, items in (
            ("Hitos", by_project(snap.milestones, project)),
            ("Riesgos", by_project(snap.risks, project)),
            ("Reuniones", by_project(snap.meetings, project)),
            ("Actas", by_project(snap.actas, project)),
            ("Documentos", [d for d in snap.documents if d.project == project]),
        ):
            if items:
                sections += ["", f"## {title}", *(_item_line(i) for i in items)]
        if open_tasks:
            sections += ["", f"## Tareas abiertas ({len(open_tasks)})"]
            sections += [_task_line(t, as_node=id(t) in task_nodes) for t in open_tasks[:30]]
        rels = [_rel("pertenece-a", "empresa", company)]
        rels += [_rel("equipo", "persona", p) for p in people]
        pages.append(
            Page(
                _project_path(company, project),
                _entity("proyecto", project, ["proyecto"], rels, company=company),
                "\n".join(sections),
            )
        )

    # Hitos, riesgos, reuniones y tareas que pesan: hojas del árbol, dentro de su proyecto.
    # Los documentos son de la red (los cruza el RAG), así que se quedan en su carpeta.
    leaves: list[tuple[str, str, list[Item]]] = [
        ("hito", "hitos", snap.milestones),
        ("riesgo", "riesgos", snap.risks),
        ("reunion", "reuniones", snap.meetings),
        ("tarea", "tareas", [t for t in snap.tasks if id(t) in task_nodes]),
        ("documento", "documentos", snap.documents),
    ]
    for kind, folder, items in leaves:
        for item in items:
            name = _item_note(item)
            parent = item.project or item.company
            header = f"{kind.capitalize()} de {link(parent)}" if parent else "Documentación general"
            lines = [f"# {item.title}", "", header]
            facts = [
                ("Fecha", item.date),
                ("Estado", item.status),
                ("Personas", ", ".join(link(p) for p in item.people)),
                ("Enlace", f"[OpenProject]({item.url})" if item.url else ""),
            ]
            lines += ["", *(f"- **{k}:** {v}" for k, v in facts if v)]
            if item.detail:
                lines += ["", item.detail]
            if kind == "reunion":
                for acta in snap.actas:
                    if acta.project == item.project and acta.date == item.date:
                        lines += ["", f"Acta: {link(_item_note(acta), acta.title)}"]
            rels = [_rel("pertenece-a", "proyecto", item.project)] if item.project else []
            rels += [_rel("responsable", "persona", p) for p in item.people]
            company = company_of(item.project) or item.company
            path = (
                f"{_project_path(company, item.project)}/{folder}/{note_name(name)}"
                if item.project and company and kind != "documento"
                else f"entities/{folder}/{note_name(name)}"
            )
            pages.append(
                Page(
                    path,
                    _entity(kind, name, [kind], rels, date=item.date, status=item.status),
                    "\n".join(lines),
                )
            )

    # Personas: la red. Cruzan proyectos y empresas a propósito.
    for person in sorted(person_items):
        roles = sorted(snap.roles.get(person, []))
        projects = sorted({i.project for _, i in person_items[person] if i.project})
        lines = [f"# {person}", "", f"Persona del {link(HUBS['equipo'][0])}"]
        if roles:
            lines.append(f"Rol: {', '.join(roles)}")
        lines += ["", "## Proyectos", *(f"- {link(p)}" for p in projects)]
        for kind, title in (
            ("tarea", "Tareas"),
            ("hito", "Hitos"),
            ("riesgo", "Riesgos"),
            ("reunion", "Reuniones"),
            ("acta", "Actas"),
        ):
            items = [i for k, i in person_items[person] if k == kind]
            if not items:
                continue
            lines += ["", f"## {title}"]
            if kind == "tarea":
                lines += [
                    _task_line(i, with_project=True, as_node=id(i) in task_nodes) for i in items
                ]
            else:
                lines += [_item_line(i, with_project=True) for i in items]
        pages.append(
            Page(
                f"entities/personas/{note_name(person)}",
                _entity(
                    "persona", person, ["persona"],
                    [_rel("participa-en", "proyecto", p) for p in projects],
                    privacyTier="private",
                ),
                "\n".join(lines),
            )
        )  # fmt: skip

    # Conceptos: índices por proyecto. Enlazan al proyecto, nunca a cada ítem: así el
    # concepto sigue siendo navegable sin arrastrar una arista por riesgo de cada empresa.
    hub_items = {
        "riesgos": snap.risks,
        "hitos": snap.milestones,
        "reuniones": snap.meetings,
        "documentos": snap.documents,
    }
    for hub, (title, description) in HUBS.items():
        if hub == "equipo":
            counts = {p: len(people) for p, people in project_people.items() if p and people}
            unit = ("persona", "personas")
        else:
            counts = Counter(i.project for i in hub_items[hub] if i.project)
            unit = (hub.rstrip("s"), hub)
        body = [f"# {title}", "", description, "", f"Parte de [[{ROOT_NOTE}]]."]
        if counts:
            body += ["", "## Por proyecto"]
            body += [
                f"- {link(project)} — {n} {unit[0] if n == 1 else unit[1]}"
                for project, n in sorted(counts.items())
            ]
        front = {"pageType": "concept", "id": f"concept.{_slug(title)}", "title": title}
        pages.append(Page(f"concepts/{title}", {**front, "tags": ["concepto"]}, "\n".join(body)))

    lines = [
        f"# {ROOT_NOTE}",
        "",
        "Mapa de lo que Jarvis sabe de tus proyectos. Se regenera solo; escribe tus notas "
        "fuera del bloque generado. Abre la **vista de grafo** para verlo como red.",
        "",
        "## Empresas",
        *([f"- {link(c)}" for c in sorted(snap.companies)] or ["- Ninguna todavía."]),
        "",
        "## Conceptos",
        *(f"- {link(t)}" for t, _ in HUBS.values()),
        "",
        "## Otros",
        "- [[SERVICIOS|Servicios de Jarvis]]",
    ]
    pages.append(Page(ROOT_NOTE, {"title": ROOT_NOTE, "tags": ["jarvis"]}, "\n".join(lines)))
    return pages


# --- Escritura ---------------------------------------------------------------------------


def _merge(existing: str | None, page: Page) -> str:
    """Frontmatter y bloque gestionado nuevos; lo escrito fuera del bloque se conserva."""
    block = f"{START}\n{page.body}\n{END}"
    after = "\n"
    if existing and START in existing and END in existing:
        after = existing.split(END, 1)[1]
    return f"{_frontmatter({**page.front, 'generatedBy': 'jarvis-red'})}\n\n{block}{after}"


def _acta_block(acta: Item, snap: Snapshot) -> str:
    info = snap.projects.get(acta.project, {})
    parts = [
        f"Proyecto: {link(acta.project)}" if acta.project else "",
        f"Empresa: {link(info['company'])}" if info else "",
    ]
    people = ", ".join(link(p) for p in dict.fromkeys(acta.people))
    lines = [p for p in parts if p] + ([f"Personas: {people}"] if people else [])
    return "\n".join(["## Red", *lines])


# Carpetas planas de la versión anterior, ahora repartidas por el árbol de cada proyecto.
LEGACY_FOLDERS = ("proyectos", "hitos", "riesgos", "reuniones", "tareas")


def _legacy_path(path: str) -> str | None:
    """Dónde vivía esta nota cuando todo era plano (`entities/<tipo>/<nota>`), o None."""
    parts = path.split("/")
    if len(parts) < 4 or parts[:2] != ["entities", "empresas"]:
        return None
    if len(parts) == 4:  # entities/empresas/<Empresa>/<Proyecto>
        return f"entities/proyectos/{parts[3]}"
    if len(parts) == 6 and parts[4] in LEGACY_FOLDERS:  # .../<Proyecto>/<tipo>/<nota>
        return f"entities/{parts[4]}/{parts[5]}"
    return None


def _migrate(vault: Path, page: Page) -> None:
    """Mueve la nota plana anterior a su sitio del árbol, con lo que hayas escrito en ella.
    Los enlaces `[[Nombre]]` de Obsidian no llevan carpeta, así que mover no los rompe."""
    legacy = _legacy_path(page.path)
    target = vault / f"{page.path}.md"
    if not legacy or target.exists():
        return
    old = vault / f"{legacy}.md"
    if old.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        old.replace(target)


def write_pages(vault: Path, pages: list[Page], snap: Snapshot) -> int:
    """Escribe las notas que cambian. Devuelve cuántas se escribieron."""
    written = 0
    for page in pages:
        _migrate(vault, page)
        target = vault / f"{page.path}.md"
        existing = target.read_text(encoding="utf-8") if target.exists() else None
        if existing is not None and "generatedBy" not in existing and START not in existing:
            continue  # nota humana con el mismo nombre: no se toca
        content = _merge(existing, page)
        if content != existing:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".md.tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(target)
            written += 1
    for acta in snap.actas:
        target = vault / f"{acta.id}.md"
        text = target.read_text(encoding="utf-8")
        block = f"{START}\n{_acta_block(acta, snap)}\n{END}"
        if START in text and END in text:
            new = text.split(START, 1)[0] + block + text.split(END, 1)[1]
        else:
            new = text.rstrip("\n") + "\n\n" + block + "\n"
        if new != text:
            target.write_text(new, encoding="utf-8")
            written += 1
    for folder in LEGACY_FOLDERS:
        legacy = vault / "entities" / folder
        if legacy.is_dir() and not any(legacy.iterdir()):
            legacy.rmdir()
    return written


# --- Memoria escrita por Jarvis --------------------------------------------------------

NOTES_HEADING = "## Notas"
# Empresas, proyectos (dentro de su empresa), personas y temas generales: sobre eso se
# pueden anotar cosas. Las directivas de Jarvis no: son una copia de su MEMORY.md.
TOPICS_DIR = "memoria"
DIRECTIVES_NOTE = f"{TOPICS_DIR}/Directivas de Jarvis"
REMEMBER_GLOBS = (
    "entities/empresas/*.md",
    "entities/empresas/*/*.md",
    "entities/personas/*.md",
    f"{TOPICS_DIR}/*.md",
)
NEW_NOTE_DIRS = {"persona": "entities/personas", "tema": TOPICS_DIR}


def _rememberable(vault: Path) -> list[Path]:
    directives = vault / f"{DIRECTIVES_NOTE}.md"
    notes = [p for pattern in REMEMBER_GLOBS for p in sorted(vault.glob(pattern))]
    return [p for p in notes if p != directives]


def find_note(vault: Path, about: str) -> Path:
    """Nota de un proyecto, empresa, persona o tema por su nombre (sin tildes ni mayúsculas)."""
    notes = _rememberable(vault)
    wanted = _key(about)
    for matches in (
        [p for p in notes if _key(p.stem) == wanted],
        [p for p in notes if wanted and wanted in _key(p.stem)],
    ):
        if len(matches) == 1:
            return matches[0]
        if matches:
            names = ", ".join(p.stem for p in matches)
            raise LookupError(f"«{about}» es ambiguo: {names}.")
    names = ", ".join(p.stem for p in notes) or "ninguna (¿está activa la red de conocimiento?)"
    raise LookupError(
        f"No hay nota de «{about}». Hay: {names}. Para crearla, repite con "
        "new='persona' (una persona) o new='tema' (un tema general)."
    )


def _new_note(vault: Path, about: str, kind: str) -> Path:
    if kind not in NEW_NOTE_DIRS:
        raise LookupError(f"new debe ser 'persona' o 'tema', no «{kind}».")
    name = note_name(about)
    if _key(name) == _key(Path(DIRECTIVES_NOTE).name):
        raise LookupError("Las directivas se editan en MEMORY.md, no con jarvis_remember.")
    note = vault / NEW_NOTE_DIRS[kind] / f"{name}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    # Bloque gestionado vacío: si la red genera después esta persona, lo rellena sin
    # tocar las notas (una nota sin bloque sería "humana" y la red no la tocaría).
    note.write_text(f"{START}\n# {name}\n{END}\n", encoding="utf-8")
    return note


def remember(
    vault: Path, about: str, text: str, today: datetime.date | None = None, new: str = ""
) -> Path:
    """Añade una nota fechada fuera del bloque generado de la nota de `about`: se conserva
    al regenerar la red, sale en Obsidian y en la wiki de OpenProject. Con `new`
    ("persona" o "tema") crea la nota si aún no existe."""
    try:
        note = find_note(vault, about)
    except LookupError:
        if not new:
            raise
        note = _new_note(vault, about, new)
    content = note.read_text(encoding="utf-8")
    line = f"- {(today or datetime.date.today()).isoformat()}: {' '.join(text.split())}"
    head, sep, tail = content.partition(END) if END in content else (content, "", "")
    if NOTES_HEADING in tail:
        tail = tail.rstrip("\n") + f"\n{line}\n"
    else:
        tail = tail.rstrip("\n") + f"\n\n{NOTES_HEADING}\n\n{line}\n"
    note.write_text(head + sep + tail, encoding="utf-8")
    return note


def mirror_directives(workspace: Path, vault: Path) -> bool:
    """Copia de solo lectura del MEMORY.md de Jarvis (sus directivas, que OpenClaw le carga
    en cada conversación) en el vault, para verla en Obsidian. Devuelve si cambió."""
    source = workspace / "MEMORY.md"
    if not source.is_file():
        return False
    target = vault / f"{DIRECTIVES_NOTE}.md"
    content = (
        f"{_frontmatter({'generatedBy': 'jarvis-directivas'})}\n\n"
        "> Copia de `MEMORY.md` de Jarvis: los cambios hechos aquí se pierden. "
        "Para cambiar una directiva, pídeselo a Jarvis.\n\n" + source.read_text(encoding="utf-8")
    )
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True


# --- Ejecución ---------------------------------------------------------------------------


def _documents() -> list[dict]:
    import httpx

    token = os.environ.get("JARVIS_API_INTERNAL_TOKEN", "")
    url = os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000")
    try:
        response = httpx.get(
            f"{url}/v1/documents", headers={"Authorization": f"Bearer {token}"}, timeout=30
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"red: sin documentos del RAG ({exc})", file=sys.stderr)
        return []
    return [d for d in response.json()["documents"] if d.get("status") == "indexed"]


def refresh(vault: Path) -> int:
    from packages.openproject.client import OpenProjectClient
    from packages.openproject.config import config_from_env

    config = config_from_env()
    op = OpenProjectClient(config) if config else None
    snap = collect(op, _documents(), vault, os.environ.get("JARVIS_OWNER_NAME", ""))
    return write_pages(vault, build_pages(snap), snap)


def main() -> None:
    parser = argparse.ArgumentParser(description=next(iter((__doc__ or "").splitlines()), None))
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--every", type=int, default=0, help="segundos entre pasadas (0 = una)")
    parser.add_argument("--workspace", type=Path, help="workspace de OpenClaw (su MEMORY.md)")
    args = parser.parse_args()
    while True:
        if args.vault.is_dir():
            try:
                n = refresh(args.vault)
                if n:
                    print(f"red: {n} notas actualizadas", flush=True)
                if args.workspace and mirror_directives(args.workspace, args.vault):
                    print("red: directivas copiadas al vault", flush=True)
            except Exception as exc:  # noqa: BLE001 — un fallo no debe parar el bucle
                print(f"red: error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        else:
            print(f"red: no existe el vault {args.vault}", file=sys.stderr, flush=True)
        if not args.every:
            return
        time.sleep(args.every)


if __name__ == "__main__":
    main()
