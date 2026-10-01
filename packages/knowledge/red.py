"""Memoria de Jarvis en el vault de Obsidian, como un solo árbol (docs/OBSIDIAN.md).

Convierte lo que Jarvis sabe (OpenProject, documentos del RAG, actas y su MEMORY.md) en
notas enlazadas para que Obsidian las muestre y el wiki de OpenClaw (memory-wiki) las use
como memoria estructurada (`pageType`, `relationships` en el frontmatter).

La regla es un **árbol**: cada nota cuelga de una sola nota padre (la carpeta es el árbol)
y solo enlaza con ella y con sus hijas. Desde el núcleo, `🧭 Mapa de Jarvis`:

    🧭 Mapa de Jarvis
    ├── 🗂 Empresas            entities/Empresas/
    │   └── 🏢 Empresa
    │       ├── 👥 Equipo de…  → 👤 personas que trabajan con esa empresa
    │       ├── 🗃 Documentos de…
    │       └── 📁 Proyecto
    │           └── 🏁 Hitos · ⚠️ Riesgos · 📅 Reuniones (→ 📝 su acta) · ✅ Tareas · 🗃 Documentos
    ├── 📚 Conocimiento        concepts/Conocimiento/
    │   ├── 🗂 Metodologías  → 📐 cada una, con sus documentos de referencia
    │   ├── 🗃 Documentación general · 🗂 Temas · 🧠 Directivas de Jarvis
    ├── 🕸 Nexos               entities/Nexos/  → 🔗 personas que trabajan con varias empresas
    ├── 👥 Contactos           personas que aún no están en ninguna empresa
    └── 📅 Agenda              reuniones sin proyecto

Lo que une dos ramas no es un enlace suelto entre hojas: es un **nexo**, una nota con
varias relaciones que hace de puente. Una persona que trabaja con dos empresas no vive en
ninguna: es `🔗 Persona` en Nexos, y enlaza con el equipo de cada empresa explicando el
motivo. Una metodología (`📐 PMI`) es el nexo entre el conocimiento y los proyectos que la
usan. Las hojas no enlazan con personas ni con conceptos: los nombran en texto. Las
relaciones completas siguen en el frontmatter (`relationships`), que es lo que lee Jarvis
y que no dibuja aristas en el grafo de Obsidian.

Todo es local: lee OpenProject, la API de Jarvis y el vault, y escribe Markdown. Cada nota
generada tiene un bloque gestionado entre marcas; lo que escribas fuera se conserva, y la
nota se mueve con lo tuyo si cambia de sitio (se reconoce por su `id`). No borra nada: si
algo desaparece de OpenProject, su nota se queda hasta que la borres.

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
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from packages.core.directives import methodology_from_metadata, methodology_id, parse_directives

START = "<!-- jarvis:red:start -->"
END = "<!-- jarvis:red:end -->"
# Proyecto de OpenProject con las reuniones sin proyecto (CALENDAR_PROVIDER=openproject).
AGENDA = os.environ.get("OPENPROJECT_CALENDAR_PROJECT", "Agenda")

# Núcleo y ramas. Las carpetas cuelgan de entities/ y concepts/ porque memory-wiki solo
# busca en ellas (además de sources/, syntheses/ y reports/).
CORE = "🧭 Mapa de Jarvis"
COMPANIES_DIR = "entities/Empresas"
NEXUS_DIR = "entities/Nexos"
CONTACTS_DIR = "entities/Contactos"
AGENDA_DIR = "entities/Agenda"
KNOWLEDGE_DIR = "concepts/Conocimiento"
METHODOLOGIES_DIR = f"{KNOWLEDGE_DIR}/Metodologías"
GENERAL_DOCS_DIR = f"{KNOWLEDGE_DIR}/Documentación general"
TOPICS_DIR = f"{KNOWLEDGE_DIR}/Temas"
DIRECTIVES_NOTE = f"{KNOWLEDGE_DIR}/🧠 Directivas de Jarvis"
# Dónde está cada empresa y proyecto, para openproject-wiki-sync y las actas.
TREE_INDEX = ".jarvis/arbol.json"

BRANCHES = {
    "empresas": (f"{COMPANIES_DIR}/🗂 Empresas", "Empresas"),
    "conocimiento": (f"{KNOWLEDGE_DIR}/📚 Conocimiento", "Conocimiento"),
    "nexos": (f"{NEXUS_DIR}/🕸 Nexos", "Nexos"),
    "contactos": (f"{CONTACTS_DIR}/👥 Contactos", "Contactos"),
    "agenda": (f"{AGENDA_DIR}/📅 Agenda", "Agenda"),
    "metodologias": (f"{METHODOLOGIES_DIR}/🗂 Metodologías", "Metodologías"),
    "documentacion": (f"{GENERAL_DOCS_DIR}/🗃 Documentación general", "Documentación general"),
    "temas": (f"{TOPICS_DIR}/🗂 Temas", "Temas"),
}
# Ramas de cada proyecto: tipo -> (icono, carpeta y título del grupo, singular).
PROJECT_GROUPS = {
    "hito": ("🏁", "Hitos", "hito"),
    "riesgo": ("⚠️", "Riesgos", "riesgo"),
    "reunion": ("📅", "Reuniones", "reunión"),
    "tarea": ("✅", "Tareas", "tarea"),
    "documento": ("🗃", "Documentos", "documento"),
}
ICONS = {
    "empresa": "🏢",
    "proyecto": "📁",
    "persona": "👤",
    "nexo": "🔗",
    "hito": "🏁",
    "riesgo": "⚠️",
    "reunion": "📅",
    "tarea": "✅",
    "documento": "📄",
    "acta": "📝",
    "metodologia": "📐",
    "tema": "💡",
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
    """Hito, riesgo, tarea, reunión, documento o acta."""

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
    methodology: str = ""  # solo en documentos


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
    owner: str = ""  # el propietario es el núcleo: no tiene nota de persona
    methods: dict[str, str] = field(default_factory=dict)  # metodología -> reglas
    project_methods: dict[str, list[str]] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    has_directives: bool = False


# --- Utilidades --------------------------------------------------------------------------


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def note_name(text: str, limit: int = 80) -> str:
    """Nombre de archivo válido y legible (es la etiqueta del nodo en el grafo)."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", text)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:limit].rstrip(" .") or "sin título"


def link(path: str, alias: str = "") -> str:
    """Enlace con la ruta completa: los nombres solo tienen que ser únicos en su carpeta."""
    return f"[[{path}|{alias or path.rsplit('/', 1)[-1]}]]"


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


def _front_value(text: str, key: str) -> str:
    if not text.startswith("---\n"):
        return ""
    head = text.split("\n---", 1)[0]
    match = re.search(rf"^{key}:\s*(.+)$", head, re.MULTILINE)
    if not match:
        return ""
    try:
        return str(json.loads(match.group(1)))
    except ValueError:
        return match.group(1).strip().strip('"')


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


def _plural(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def pretty_document_name(filename: str) -> str:
    """«input-PMBOK-7Ed---<uuid>.pdf» -> «PMBOK 7Ed»: el nombre que se ve en el grafo."""
    name = re.sub(r"(---[0-9a-f-]{36})?\.[a-z0-9]+$", "", filename).removeprefix("input-")
    name = re.sub(r"_s_", "'s ", name)
    name = re.sub(r"_+|(?<=[^\W\d_])-|-(?=[^\W\d_])", " ", name)  # no en fechas
    name = re.sub(r"\s+", " ", name).strip()
    return name[:1].upper() + name[1:]


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


ACTA_GLOBS = (
    "sources/proyectos/*/actas/*.md",  # donde las deja Jarvis si el proyecto aún no está
    f"{COMPANIES_DIR}/*/*/Reuniones/*.md",
    f"{AGENDA_DIR}/*.md",
)


def _is_acta(text: str) -> bool:
    return "\n- **Fecha:**" in text and not _front_value(text, "generatedBy")


def read_actas(vault: Path) -> list[Item]:
    """Actas guardadas por Jarvis, estén aún en sources/ o ya en su sitio del árbol."""
    actas = []
    for path in sorted({p for pattern in ACTA_GLOBS for p in vault.glob(pattern)}):
        text = path.read_text(encoding="utf-8")
        if not _is_acta(text):
            continue
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


def read_methods(text: str) -> dict[str, str]:
    """Zonas `### <Metodología>` de la sección «Metodologías» de MEMORY.md y sus reglas."""
    methods: dict[str, list[str]] = {}
    zone, current = "", None
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            zone, current = _slug(line[3:]), None
        elif zone == "metodologias" and line.startswith("### "):
            current = line[4:].strip()
            methods[current] = []
        elif current is not None:
            methods[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in methods.items()}


def _existing_names(vault: Path, pattern: str, icon: str) -> list[str]:
    """Notas creadas con jarvis_remember (temas, metodologías) aunque la red no las genere."""
    return [p.stem.removeprefix(icon).strip() for p in sorted(vault.glob(pattern))]


def collect(
    op,
    documents: list[dict],
    vault: Path,
    owner_name: str = "",
    memory: str | None = None,
) -> Snapshot:
    """Reúne lo que hay en OpenProject, el RAG, las actas del vault y MEMORY.md."""
    snap = Snapshot(owner=owner_name, has_directives=memory is not None)
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
            )
    for doc in documents:
        meta = doc.get("doc_metadata") or {}
        snap.documents.append(
            Item(
                id=doc["id"],
                title=pretty_document_name(doc["filename"]),
                project=meta.get("project", ""),
                company=meta.get("company", ""),
                date=str(doc.get("created_at", ""))[:10],
                status=doc.get("status", ""),
                detail=doc["filename"],
                methodology=methodology_from_metadata(meta),
            )
        )
    # Empresas y proyectos que solo tienen documentos (sin proyecto en OpenProject).
    for doc in snap.documents:
        if doc.company and doc.company not in snap.companies:
            snap.companies[doc.company] = ""
        if doc.project and doc.project not in snap.projects:
            snap.projects[doc.project] = {"company": doc.company, "url": "", "gantt": ""}
    # Proyectos sin empresa (no deberían existir): cuelgan de una empresa con su nombre.
    for project, info in snap.projects.items():
        if not info["company"]:
            info["company"] = project
            snap.companies.setdefault(project, "")
    for doc in snap.documents:
        if doc.project:
            doc.company = snap.projects[doc.project]["company"]
    snap.actas = read_actas(vault)
    # Las actas indexadas en el RAG ya son notas del vault: sin nodo de documento aparte.
    acta_files = {_slug(a.id.rsplit("/", 1)[-1]) for a in snap.actas}
    snap.documents = [d for d in snap.documents if _slug(Path(d.detail).stem) not in acta_files]
    for acta in snap.actas:
        acta.company = snap.projects.get(acta.project, {}).get("company", "")
        for person, role in json.loads(acta.detail or "{}").items():
            if role:
                snap.roles[person].add(role)
    if owner_name:
        _merge_owner(snap, owner_name)
    _read_knowledge(snap, vault, memory or "")
    return snap


def _read_knowledge(snap: Snapshot, vault: Path, memory: str) -> None:
    """Metodologías (MEMORY.md, documentos y notas propias), su uso por proyecto y temas."""
    methods = read_methods(memory)
    names = {methodology_id(n): n for n in methods}
    extra = [d.methodology for d in snap.documents if d.methodology]
    extra += _existing_names(vault, f"{METHODOLOGIES_DIR}/*/📐 *.md", "📐")
    for name in extra:
        if methodology_id(name) not in names:
            names[methodology_id(name)] = name
            methods[name] = ""
    for doc in snap.documents:  # mismo nombre que la zona de MEMORY.md ("pmi" -> "PMI")
        if doc.methodology:
            doc.methodology = names[methodology_id(doc.methodology)]
    snap.methods = dict(sorted(methods.items(), key=lambda kv: _key(kv[0])))
    directives = parse_directives(memory)
    for project, info in snap.projects.items():
        ids = directives.for_project(info["company"], project)
        if ids:
            snap.project_methods[project] = [names.get(i, i) for i in ids]
    snap.topics = _existing_names(vault, f"{TOPICS_DIR}/💡 *.md", "💡")


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


# --- Rutas del árbol ---------------------------------------------------------------------


def _company_dir(company: str) -> str:
    return f"{COMPANIES_DIR}/{note_name(company)}"


def _company_note(company: str) -> str:
    return f"{_company_dir(company)}/🏢 {note_name(company)}"


def _project_dir(company: str, project: str) -> str:
    """El proyecto vive dentro de la carpeta de su empresa: la carpeta es el árbol."""
    return f"{_company_dir(company)}/{note_name(project)}"


def _project_note(company: str, project: str) -> str:
    return f"{_project_dir(company, project)}/📁 {note_name(project)}"


def _project_group(company: str, project: str, kind: str) -> str:
    icon, label, _ = PROJECT_GROUPS[kind]
    return f"{_project_dir(company, project)}/{label}/{icon} {label} de {note_name(project, 60)}"


def _team_note(company: str) -> str:
    return f"{_company_dir(company)}/Equipo/👥 Equipo de {note_name(company, 60)}"


def _company_docs_note(company: str) -> str:
    return f"{_company_dir(company)}/Documentos/🗃 Documentos de {note_name(company, 60)}"


def _method_note(name: str) -> str:
    return f"{METHODOLOGIES_DIR}/{note_name(name)}/📐 {note_name(name)}"


def acta_file_name(date: str, title: str) -> str:
    """Nombre del archivo de un acta: «📝 2026-03-02 · Kick-off tienda online»."""
    title = re.sub(r"^acta\s*:?\s*", "", title, flags=re.IGNORECASE)
    return f"{ICONS['acta']} {date} · {note_name(title, 60)}" if date else f"📝 {note_name(title)}"


BLOCKED = ("bloquead", "blocked", "en espera", "on hold", "detenid", "parad")


def _task_is_node(task: Item, acta_tasks: set[str]) -> bool:
    """Una tarea pesa —y entra en el árbol— si está bloqueada o si la nombra un acta."""
    if any(mark in _key(task.status) for mark in BLOCKED):
        return True
    return _key(task.title) in acta_tasks


# --- Notas -------------------------------------------------------------------------------


@dataclass
class Page:
    path: str  # relativa al vault, sin .md
    front: dict
    body: str
    # Solo en las actas: dónde está ahora el archivo. El acta no se genera; se mueve a su
    # sitio del árbol y se le añade el bloque gestionado (`body`).
    acta_from: str = ""


def _entity(kind: str, title: str, page_id: str, relationships: list[dict], **extra) -> dict:
    return {
        "pageType": "entity",
        "entityType": kind,
        "id": page_id,
        "title": title,
        "tags": [kind],
        "relationships": relationships,
        **extra,
    }


def _group(title: str, page_id: str, tag: str) -> dict:
    """Notas índice (núcleo, ramas y grupos): estructura, no memoria."""
    return {"id": page_id, "title": title, "tags": ["jarvis", tag]}


def _rel(kind: str, target_id: str, title: str) -> dict:
    return {"targetId": target_id, "targetTitle": title, "kind": kind}


def _company_id(company: str) -> str:
    return f"entity.empresa.{_slug(company)}"


def _project_id(company: str, project: str) -> str:
    return f"entity.proyecto.{_slug(company)}.{_slug(project)}"


def _person_id(person: str) -> str:
    return f"entity.persona.{_slug(person)}"


def _method_id(method: str) -> str:
    return f"concept.metodologia.{methodology_id(method)}"


def _label(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _mermaid(edges: list[tuple[str, str, bool]], limit: int = 60) -> list[str]:
    """Diagrama del árbol (Obsidian y OpenProject lo dibujan): (padre, hijo, ¿nexo?)."""
    if not edges:
        return []
    ids: dict[str, str] = {}

    def node(label: str) -> str:
        if label in ids:
            return ids[label]
        ids[label] = f"n{len(ids)}"
        return f'{ids[label]}["{label.replace(chr(34), "#quot;")}"]'

    lines = ["```mermaid", "flowchart LR"]
    for parent, child, nexus in edges[:limit]:
        lines.append(f"  {node(parent)} {'-.-' if nexus else '-->'} {node(child)}")
    if len(edges) > limit:
        lines.append(f'  {ids[edges[0][0]]} --> more["… y {len(edges) - limit} más"]')
    return [*lines, "```"]


class _Names:
    """Nombres únicos por carpeta, sin distinguir mayúsculas (iPhone y macOS no lo hacen)."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def __call__(self, folder: str, name: str, suffix: str) -> str:
        path = f"{folder}/{note_name(name)}"
        if path.lower() in self.used:
            path = f"{folder}/{note_name(name, 68)} ({suffix})"
        self.used.add(path.lower())
        return path


def _leaf_name(kind: str, item: Item) -> str:
    if kind == "reunion" and item.date:
        return f"{ICONS['reunion']} {item.date} · {note_name(item.title, 60)}"
    return f"{ICONS[kind]} {note_name(item.title, 70)}"


def _suffix(item: Item) -> str:
    return f"OP-{item.id}" if item.id.isdigit() else item.id[:8]


def _work_line(kind: str, item: Item) -> str:
    """Una línea de texto (sin enlaces): lo que hace una persona, sin cruzar ramas."""
    parts = [f"{ICONS[kind]} {item.title}"]
    if item.date:
        parts.append(("vence " if kind == "tarea" else "") + item.date)
    if item.status:
        parts.append(item.status)
    return "- " + " · ".join(parts)


LEAF_LABELS = {
    "hito": "Hito",
    "riesgo": "Riesgo",
    "reunion": "Reunión",
    "tarea": "Tarea",
    "documento": "Documento",
}


def _leaf(path: str, kind: str, item: Item, parent: str, company: str = "") -> Page:
    """Hoja del árbol: enlaza solo con su padre; personas y lugares van en texto."""
    where = " · ".join(x for x in (item.project, item.company or company) if x)
    facts = [
        ("Proyecto" if item.project else "Empresa", where),
        ("Fecha", item.date),
        ("Estado", item.status),
        ("Personas" if kind == "reunion" else "Responsable", ", ".join(item.people)),
        ("OpenProject", f"[#{item.id}]({item.url})" if item.url else ""),
        ("Metodología", item.methodology),
    ]
    lines = [f"# {_label(path)}", "", f"{LEAF_LABELS[kind]} de {link(parent)}", ""]
    lines += [f"- **{k}:** {v}" for k, v in facts if v]
    if item.detail and kind != "documento":  # en documentos es el nombre del archivo
        lines += ["", item.detail]
    rels = []
    if item.project:
        rels.append(_rel("pertenece-a", _project_id(item.company, item.project), item.project))
    elif item.company:
        rels.append(_rel("pertenece-a", _company_id(item.company), item.company))
    rels += [_rel("responsable", _person_id(p), p) for p in item.people]
    if item.methodology:
        rels.append(_rel("metodologia", _method_id(item.methodology), item.methodology))
    page_id = f"entity.{kind}.{'op-' + item.id if item.id.isdigit() else _slug(item.id)}"
    front = _entity(kind, item.title, page_id, rels, date=item.date, status=item.status)
    return Page(path, front, "\n".join(lines))


def _note(path: str, front: dict, lines: list[str]) -> Page:
    return Page(path, front, "\n".join(lines))


def _branch(key: str, parent: str, lines: list[str]) -> Page:
    path = BRANCHES[key][0]
    return _note(
        path,
        _group(_label(path), f"jarvis.{key}", key),
        [f"# {_label(path)}", "", f"Rama de {link(parent)}", "", *lines],
    )


def build_pages(snap: Snapshot) -> list[Page]:
    """Todas las notas del árbol a partir de una instantánea (función pura)."""
    pages: list[Page] = []
    unique = _Names()
    owner = _key(snap.owner)
    core = CORE

    # --- Quién trabaja dónde ----------------------------------------------------------------
    person_work: dict[str, list[tuple[str, Item]]] = defaultdict(list)
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
                if _key(person) != owner:
                    person_work[person].append((kind, item))
    person_companies = {
        person: sorted({i.company for _, i in work if i.company}, key=_key)
        for person, work in person_work.items()
    }

    def person_path(person: str) -> str:
        companies = person_companies[person]
        if len(companies) == 1:
            return f"{_company_dir(companies[0])}/Equipo/👤 {note_name(person)}"
        if companies:
            return f"{NEXUS_DIR}/🔗 {note_name(person)}"
        return f"{CONTACTS_DIR}/👤 {note_name(person)}"

    def work_lines(person: str) -> list[str]:
        by_place: dict[str, list[str]] = defaultdict(list)
        for kind, item in person_work[person]:
            place = " › ".join(x for x in (item.company, item.project) if x) or "Agenda"
            by_place[place].append(_work_line(kind, item))
        return [
            line for place, work in sorted(by_place.items()) for line in ("", f"### {place}", *work)
        ]

    def why(person: str, company: str) -> str:
        """Por qué una persona une esta empresa: su rol, sus proyectos y lo que hace."""
        work = [(k, i) for k, i in person_work[person] if i.company == company]
        counts: dict[str, int] = defaultdict(int)
        for kind, _ in work:
            counts[kind] += 1
        names = {
            "tarea": ("tarea", ""),
            "hito": ("hito", ""),
            "riesgo": ("riesgo", ""),
            "reunion": ("reunión", "reuniones"),
            "acta": ("acta", ""),
        }
        what = ", ".join(_plural(n, *names[k]) for k, n in counts.items())
        projects = ", ".join(sorted({i.project for _, i in work if i.project}))
        roles = ", ".join(sorted(snap.roles.get(person, [])))
        parts = [roles, f"en {projects}" if projects else "", what]
        return " · ".join(p for p in parts if p)

    def people_of(project: str) -> list[str]:
        items = [*snap.tasks, *snap.milestones, *snap.risks, *snap.meetings, *snap.actas]
        found = {p for i in items if i.project == project for p in i.people}
        return sorted(found, key=_key)

    company_projects: dict[str, list[str]] = defaultdict(list)
    method_projects: dict[str, list[str]] = defaultdict(list)
    for project, info in sorted(snap.projects.items(), key=lambda kv: _key(kv[0])):
        company_projects[info["company"]].append(project)
        for method in snap.project_methods.get(project, []):
            method_projects[method].append(project)

    def project_note(project: str) -> str:
        return _project_note(snap.projects[project]["company"], project)

    # --- Ramas de cada proyecto: hitos, riesgos, reuniones, tareas y documentos ---------------
    acta_tasks = {_key(t) for acta in snap.actas for t in acta.mentions}
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)  # proyecto -> (grupo, n)
    meeting_of: dict[tuple[str, str], str] = {}  # (proyecto, fecha) -> nota de la reunión
    group_pages: dict[str, Page] = {}
    for kind, items in (
        ("hito", snap.milestones),
        ("riesgo", snap.risks),
        ("reunion", snap.meetings),
        ("tarea", snap.tasks),
        ("documento", snap.documents),
    ):
        for project in sorted({i.project for i in items if i.project in snap.projects}):
            company = snap.projects[project]["company"]
            mine = sorted(
                (i for i in items if i.project == project),
                key=lambda i: (i.date or "9", _key(i.title)),
            )
            group = _project_group(company, project, kind)
            folder = group.rsplit("/", 1)[0]
            _, label, singular = PROJECT_GROUPS[kind]
            lines: list[str] = []
            if kind == "tarea":
                # Las tareas solo son nota si pesan; el resto, líneas del grupo.
                open_tasks = [t for t in mine if _key(t.status) not in CLOSED]
                heavy = [t for t in mine if _task_is_node(t, acta_tasks)]
                if not open_tasks and not heavy:
                    continue
                paths = {}
                for task in heavy:
                    paths[task.id] = unique(folder, _leaf_name("tarea", task), _suffix(task))
                    pages.append(_leaf(paths[task.id], "tarea", task, group))
                count, unit = len(open_tasks), ("abierta", "abiertas")
                for task in open_tasks[:40]:
                    title = link(paths[task.id], task.title) if task.id in paths else task.title
                    parts = [f"[#{task.id}]({task.url}) {title}" if task.url else title]
                    parts += [x for x in (task.date and f"vence {task.date}", task.status) if x]
                    parts += [", ".join(task.people)] if task.people else []
                    lines.append("- " + " · ".join(parts))
                closed = [t for t in heavy if t not in open_tasks]
                if closed:  # cerradas que conviene recordar (las nombra un acta)
                    lines += ["", "Cerradas que nombra un acta:"]
                    lines += [f"- {link(paths[t.id], t.title)} · {t.status}" for t in closed]
            else:
                count, unit = len(mine), (singular, label.lower())
                for item in mine:
                    path = unique(folder, _leaf_name(kind, item), _suffix(item))
                    if kind == "reunion":
                        meeting_of.setdefault((project, item.date), path)
                    pages.append(_leaf(path, kind, item, group))
                    extra = [x for x in (item.date if kind != "reunion" else "", item.status) if x]
                    lines.append(" · ".join([f"- {link(path)}", *extra]))
            header = f"Rama de {link(project_note(project))} · {_plural(count, *unit)}"
            page = _note(
                group,
                _group(
                    _label(group),
                    f"grupo.{kind}.{_slug(company)}." f"{_slug(project)}",
                    label.lower(),
                ),
                [f"# {_label(group)}", "", header, "", *lines],
            )
            pages.append(page)
            group_pages[group] = page
            groups[project].append((group, count))

    # --- Actas: hijas de su reunión (mismo proyecto y fecha), o del grupo de reuniones ------
    agenda = BRANCHES["agenda"][0]
    acta_children: dict[str, list[str]] = defaultdict(list)
    agenda_actas: list[str] = []
    for acta in snap.actas:
        name = _label(acta.id)
        if acta.project in snap.projects:
            company = snap.projects[acta.project]["company"]
            group = _project_group(company, acta.project, "reunion")
            if group not in group_pages:  # proyecto sin reuniones en OpenProject
                page = _note(
                    group,
                    _group(
                        _label(group),
                        f"grupo.reunion.{_slug(company)}." f"{_slug(acta.project)}",
                        "reuniones",
                    ),
                    [f"# {_label(group)}", "", f"Rama de {link(project_note(acta.project))}"],
                )
                pages.append(page)
                group_pages[group] = page
                groups[acta.project].append((group, 0))
            parent = meeting_of.get((acta.project, acta.date), group)
            path = f"{group.rsplit('/', 1)[0]}/{name}"
        else:
            parent, path = agenda, f"{AGENDA_DIR}/{name}"
            agenda_actas.append(path)
        acta_children[parent].append(path)
        where = " · ".join(x for x in (acta.project, acta.company) if x)
        block = ["## Red", f"Acta de {link(parent)}"]
        block += [f"Proyecto: {where}"] if where else []
        block += [f"Personas: {', '.join(acta.people)}"] if acta.people else []
        pages.append(Page(path, {}, "\n".join(block), acta_from=acta.id))
    for page in pages:
        if page.path in acta_children and not page.acta_from:
            page.body += "\n\n## Actas\n" + "\n".join(
                f"- {link(path)}" for path in acta_children[page.path]
            )

    # --- Proyectos ----------------------------------------------------------------------------
    order = list(PROJECT_GROUPS)
    for project, info in sorted(snap.projects.items(), key=lambda kv: _key(kv[0])):
        company = info["company"]
        note = project_note(project)
        mine = sorted(
            groups.get(project, []),
            key=lambda g: order.index(
                next(k for k, v in PROJECT_GROUPS.items() if f"/{v[1]}/" in g[0])
            ),
        )
        methods = snap.project_methods.get(project, [])
        header = f"Proyecto de {link(_company_note(company))}"
        if info["url"]:
            header += f" · [OpenProject]({info['url']}) · [Gantt]({info['gantt']})"
        lines = [f"# {_label(note)}", "", header]
        if methods:
            lines.append(f"Metodología: {' + '.join(methods)}")
        edges = [(_label(note), f"{_label(g)} ({n})", False) for g, n in mine]
        edges += [(_label(_method_note(m)), _label(note), True) for m in methods]
        if edges:
            lines += ["", *_mermaid(edges)]
        if mine:
            lines += ["", "## Ramas", *(f"- {link(g)}" for g, _ in mine)]
        people = people_of(project)
        if people:
            lines += ["", "## Equipo"]
            for person in people:
                roles = ", ".join(sorted(snap.roles.get(person, [])))
                lines.append(f"- {person}" + (f" — {roles}" if roles else ""))
        rels = [_rel("pertenece-a", _company_id(company), company)]
        rels += [_rel("equipo", _person_id(p), p) for p in people if _key(p) != owner]
        rels += [_rel("metodologia", _method_id(m), m) for m in methods]
        front = _entity("proyecto", project, _project_id(company, project), rels, company=company)
        pages.append(_note(note, front, lines))

    # --- Empresas, su equipo y su documentación -------------------------------------------------
    team: dict[str, list[str]] = defaultdict(list)
    shared: dict[str, list[str]] = defaultdict(list)
    for person, companies in sorted(person_companies.items(), key=lambda kv: _key(kv[0])):
        for company in companies:
            (team if len(companies) == 1 else shared)[company].append(person)

    companies_branch = BRANCHES["empresas"][0]
    for company, url in sorted(snap.companies.items(), key=lambda kv: _key(kv[0])):
        note = _company_note(company)
        projects = company_projects.get(company, [])
        docs = sorted(
            (d for d in snap.documents if d.company == company and not d.project),
            key=lambda d: _key(d.title),
        )
        tnote, dnote = _team_note(company), _company_docs_note(company)
        edges = [(_label(note), _label(project_note(p)), False) for p in projects]
        lines = [
            f"# {_label(note)}",
            "",
            f"Empresa de {link(companies_branch)}" + (f" · [OpenProject]({url})" * bool(url)),
        ]
        if team[company] or shared[company]:
            edges.append((_label(note), _label(tnote), False))
            edges += [(_label(tnote), _label(person_path(p)), True) for p in shared[company]]
        if docs:
            edges.append((_label(note), _label(dnote), False))
        if edges:
            lines += ["", *_mermaid(edges)]
        lines += ["", "## Proyectos"]
        for project in projects:
            facts = []
            if methods := snap.project_methods.get(project):
                facts.append(" + ".join(methods))
            open_tasks = sum(
                1 for t in snap.tasks if t.project == project and _key(t.status) not in CLOSED
            )
            if open_tasks:
                facts.append(_plural(open_tasks, "tarea abierta", "tareas abiertas"))
            if risks := sum(1 for r in snap.risks if r.project == project):
                facts.append(_plural(risks, "riesgo"))
            lines.append(
                f"- {link(project_note(project))}" + (f" — {' · '.join(facts)}" if facts else "")
            )
        if not projects:
            lines.append("- Ninguno todavía.")
        if team[company] or shared[company]:
            n = len(team[company]) + len(shared[company])
            lines += ["", "## Equipo", f"- {link(tnote)} — {_plural(n, 'persona')}"]
            tlines = []
            if team[company]:
                tlines += ["## Personas"]
                for person in team[company]:
                    roles = ", ".join(sorted(snap.roles.get(person, [])))
                    where = ", ".join(
                        sorted({i.project for _, i in person_work[person] if i.project})
                    )
                    extra = " · ".join(x for x in (roles, where) if x)
                    tlines.append(
                        f"- {link(person_path(person))}" + (f" — {extra}" if extra else "")
                    )
            if shared[company]:
                tlines += (
                    ["", "## Compartidas con otras empresas (nexos)"]
                    if tlines
                    else ["## Compartidas con otras empresas (nexos)"]
                )
                for person in shared[company]:
                    others = ", ".join(c for c in person_companies[person] if c != company)
                    tlines.append(f"- {link(person_path(person))} — también con {others}")
            pages.append(
                _note(
                    tnote,
                    _group(_label(tnote), f"grupo.equipo.{_slug(company)}", "equipo"),
                    [f"# {_label(tnote)}", "", f"Rama de {link(note)}", "", *tlines],
                )
            )
        if docs:
            lines += [
                "",
                "## Documentación",
                f"- {link(dnote)} — {_plural(len(docs), 'documento')}",
            ]
            dlines = []
            for doc in docs:
                path = unique(dnote.rsplit("/", 1)[0], _leaf_name("documento", doc), _suffix(doc))
                pages.append(_leaf(path, "documento", doc, dnote))
                dlines.append(f"- {link(path)}" + (f" · {doc.date}" if doc.date else ""))
            pages.append(
                _note(
                    dnote,
                    _group(_label(dnote), f"grupo.documentos.{_slug(company)}", "documentos"),
                    [f"# {_label(dnote)}", "", f"Rama de {link(note)}", "", *dlines],
                )
            )
        pages.append(_note(note, _entity("empresa", company, _company_id(company), []), lines))

    # --- Personas: en el equipo de su empresa, como nexo entre empresas o como contacto -----
    for person in sorted(person_work, key=_key):
        path = person_path(person)
        companies = person_companies[person]
        roles = ", ".join(sorted(snap.roles.get(person, [])))
        projects = sorted({i.project for _, i in person_work[person] if i.project in snap.projects})
        rels = [_rel("trabaja-con", _company_id(c), c) for c in companies]
        rels += [
            _rel("participa-en", _project_id(snap.projects[p]["company"], p), p) for p in projects
        ]
        front = _entity("persona", person, _person_id(person), rels, privacyTier="private")
        if len(companies) >= 2:
            front["tags"] = ["persona", "nexo"]
            lines = [
                f"# {_label(path)}",
                "",
                f"Nexo de {link(BRANCHES['nexos'][0])}: une "
                f"{_plural(len(companies), 'empresa')} a través de esta persona.",
            ]
            lines += [f"Rol: {roles}"] if roles else []
            lines += [
                "",
                *_mermaid([(_label(_team_note(c)), _label(path), True) for c in companies]),
            ]
            lines += ["", "## Por qué une estas empresas"]
            lines += [f"- {link(_team_note(c))} — {why(person, c)}" for c in companies]
            lines += ["", "## Qué hace en cada una", *work_lines(person)]
        else:
            parent = _team_note(companies[0]) if companies else BRANCHES["contactos"][0]
            lines = [f"# {_label(path)}", "", f"Persona de {link(parent)}"]
            lines += [f"Rol: {roles}"] if roles else []
            lines += ["", "## En qué participa", *work_lines(person)]
        pages.append(_note(path, front, lines))

    # --- Conocimiento: metodologías, documentación general, temas y directivas ------------------
    general = sorted(
        (d for d in snap.documents if not d.company and not d.project), key=lambda d: _key(d.title)
    )
    knowledge = BRANCHES["conocimiento"][0]
    branch_lines: dict[str, list[str]] = {}
    for method, rules in snap.methods.items():
        note = _method_note(method)
        folder = note.rsplit("/", 1)[0]
        users = method_projects.get(method, [])
        docs = [d for d in general if d.methodology == method]
        doc_paths = [unique(folder, _leaf_name("documento", d), _suffix(d)) for d in docs]
        pages += [_leaf(p, "documento", d, note) for p, d in zip(doc_paths, docs, strict=True)]
        edges = [(_label(note), _label(p), False) for p in doc_paths]
        edges += [(_label(note), _label(project_note(p)), True) for p in users]
        lines = [f"# {_label(note)}", "", f"Metodología de {link(BRANCHES['metodologias'][0])}"]
        if edges:
            lines += ["", *_mermaid(edges)]
        if rules:
            demoted = re.sub(r"^(#{1,4}) ", r"\1## ", rules, flags=re.MULTILINE)
            lines += [
                "",
                "## Reglas",
                "",
                "> Copia de su zona en MEMORY.md: para cambiarlas, pídeselo a Jarvis.",
                "",
                demoted,
            ]
        if doc_paths:
            lines += ["", "## Documentos de referencia", *(f"- {link(p)}" for p in doc_paths)]
        if users:
            lines += ["", "## Proyectos que la usan (nexo)"]
            lines += [f"- {link(project_note(p))} · {snap.projects[p]['company']}" for p in users]
        rels = [_rel("la-usa", _project_id(snap.projects[p]["company"], p), p) for p in users]
        front = {
            "pageType": "concept",
            "id": _method_id(method),
            "title": method,
            "tags": ["metodologia"],
            "relationships": rels,
        }
        pages.append(_note(note, front, lines))
        facts = [_plural(len(docs), "documento")] if docs else []
        facts += [_plural(len(users), "proyecto")] if users else []
        branch_lines.setdefault(
            "metodologias",
            [
                "Cada metodología con sus reglas y su documentación de referencia, aparte de las "
                "demás para que no se mezclen.",
                "",
            ],
        )
        branch_lines["metodologias"].append(
            f"- {link(note)}" + (f" — {', '.join(facts)}" if facts else "")
        )
    loose = [d for d in general if not d.methodology]
    for doc in loose:
        path = unique(GENERAL_DOCS_DIR, _leaf_name("documento", doc), _suffix(doc))
        pages.append(_leaf(path, "documento", doc, BRANCHES["documentacion"][0]))
        branch_lines.setdefault("documentacion", []).append(
            f"- {link(path)}" + (f" · {doc.date}" if doc.date else "")
        )
    for topic in snap.topics:
        path = f"{TOPICS_DIR}/💡 {note_name(topic)}"
        front = {
            "pageType": "concept",
            "id": f"concept.tema.{_slug(topic)}",
            "title": topic,
            "tags": ["tema"],
        }
        pages.append(
            _note(path, front, [f"# {_label(path)}", "", f"Tema de {link(BRANCHES['temas'][0])}"])
        )
        branch_lines.setdefault("temas", []).append(f"- {link(path)}")

    kedges, klines = [], []
    for key, count, unit in (
        ("metodologias", len(snap.methods), ("metodología", "metodologías")),
        ("documentacion", len(loose), ("documento", "")),
        ("temas", len(snap.topics), ("tema", "")),
    ):
        if key in branch_lines:
            pages.append(_branch(key, knowledge, branch_lines[key]))
            kedges.append((_label(knowledge), _label(BRANCHES[key][0]), False))
            klines.append(f"- {link(BRANCHES[key][0])} — {_plural(count, *unit)}")
    kedges += [
        (_label(BRANCHES["metodologias"][0]), _label(_method_note(m)), False) for m in snap.methods
    ]
    if snap.has_directives:
        kedges.append((_label(knowledge), _label(DIRECTIVES_NOTE), False))
        klines.append(f"- {link(DIRECTIVES_NOTE)} — cómo trabaja Jarvis (su MEMORY.md)")
    lines = [
        "Lo que Jarvis sabe que no es de un proyecto: los documentos de una empresa o un "
        "proyecto cuelgan de ellos.",
        "",
    ]
    lines += [*_mermaid(kedges), ""] if kedges else []
    lines += ["## Ramas", *(klines or ["- Nada todavía."])]
    pages.append(_branch("conocimiento", core, lines))

    # --- Nexos, contactos, agenda y empresas: ramas del núcleo ------------------------------
    nexus = [p for p in sorted(person_companies, key=_key) if len(person_companies[p]) >= 2]
    contacts = [p for p in sorted(person_companies, key=_key) if not person_companies[p]]
    if nexus:
        lines = [
            "Lo único que une ramas del árbol. Una persona que trabaja con varias "
            "empresas no cuelga de ninguna: está aquí y enlaza con el equipo de cada una. "
            f"Las metodologías unen proyectos desde {link(knowledge)}.",
            "",
        ]
        lines += [f"- {link(person_path(p))} — {', '.join(person_companies[p])}" for p in nexus]
        pages.append(_branch("nexos", core, lines))
    if contacts:
        lines = ["Personas que aún no trabajan con ninguna empresa.", ""]
        pages.append(
            _branch("contactos", core, lines + [f"- {link(person_path(p))}" for p in contacts])
        )
    loose_meetings = sorted(
        (m for m in snap.meetings if m.project not in snap.projects), key=lambda m: m.date
    )
    if loose_meetings or agenda_actas:
        lines = ["Reuniones y actas sin proyecto.", ""]
        for meeting in loose_meetings:
            path = unique(AGENDA_DIR, _leaf_name("reunion", meeting), _suffix(meeting))
            pages.append(_leaf(path, "reunion", meeting, agenda))
            lines.append(f"- {link(path)}" + (f" · {meeting.status}" if meeting.status else ""))
        pages.append(_branch("agenda", core, lines))  # sus actas las añade el bloque «Actas»
        if agenda_actas:
            pages[-1].body += "\n\n## Actas\n" + "\n".join(f"- {link(p)}" for p in agenda_actas)

    lines = []
    for company in sorted(snap.companies, key=_key):
        n = len(company_projects.get(company, []))
        lines.append(f"- {link(_company_note(company))} — {_plural(n, 'proyecto')}")
    pages.append(_branch("empresas", core, lines or ["- Ninguna todavía."]))

    # --- Núcleo -----------------------------------------------------------------------------
    edges = [(core, _label(companies_branch), False)]
    for company in sorted(snap.companies, key=_key):
        edges.append((_label(companies_branch), _label(_company_note(company)), False))
        edges += [
            (_label(_company_note(company)), _label(project_note(p)), False)
            for p in company_projects.get(company, [])
        ]
    edges.append((core, _label(knowledge), False))
    edges += [(_label(knowledge), _label(_method_note(m)), False) for m in snap.methods]
    for method, users in method_projects.items():
        edges += [(_label(_method_note(method)), _label(project_note(p)), True) for p in users]
    for key, present in (
        ("nexos", nexus),
        ("contactos", contacts),
        ("agenda", loose_meetings or agenda_actas),
    ):
        if present:
            edges.append((core, _label(BRANCHES[key][0]), False))
    for person in nexus:
        edges.append((_label(BRANCHES["nexos"][0]), _label(person_path(person)), False))
        edges += [
            (_label(person_path(person)), _label(_company_note(c)), True)
            for c in person_companies[person]
        ]
    n_projects = sum(len(v) for v in company_projects.values())
    lines = [
        f"# {core}",
        "",
        "Todo lo que Jarvis sabe, en un solo árbol. Cada nota cuelga de una sola rama; lo que "
        "une ramas son los **nexos** (líneas de puntos): personas que trabajan con varias "
        "empresas y metodologías que usan varios proyectos. Se regenera solo: escribe tus notas "
        "fuera del bloque generado.",
    ]
    if snap.owner:
        lines += ["", f"Propietario: {snap.owner}, el centro del mapa."]
    lines += ["", *_mermaid(edges, limit=80), "", "## Ramas"]
    lines.append(
        f"- {link(companies_branch)} — {_plural(len(snap.companies), 'empresa')}, "
        f"{_plural(n_projects, 'proyecto')}"
    )
    lines.append(
        f"- {link(knowledge)} — {_plural(len(snap.methods), 'metodología', 'metodologías')}"
        f", {_plural(len(general), 'documento')} de referencia"
    )
    if nexus:
        lines.append(f"- {link(BRANCHES['nexos'][0])} — {_plural(len(nexus), 'nexo')}")
    if contacts:
        lines.append(f"- {link(BRANCHES['contactos'][0])} — {_plural(len(contacts), 'persona')}")
    if loose_meetings or agenda_actas:
        lines.append(f"- {link(agenda)} — reuniones y actas sin proyecto")
    lines += [
        "- [[SERVICIOS|🛠 Servicios de Jarvis]]",
        "",
        "## Verlo como árbol",
        "",
        "En la **vista de grafo**: filtro `-path:reports -path:sources -file:index -file:AGENTS "
        "-file:WIKI` (quita los índices del plugin de memoria, que enlazan con todo) y un grupo "
        "de color por rama: `path:entities/Empresas`, `path:concepts/Conocimiento`, "
        "`path:entities/Nexos`. Detalle en docs/OBSIDIAN.md.",
    ]
    pages.append(_note(core, _group(core, "jarvis.mapa", "mapa"), lines))
    return pages


# --- Escritura ---------------------------------------------------------------------------


def _merge(existing: str | None, page: Page) -> str:
    """Frontmatter y bloque gestionado nuevos; lo escrito fuera del bloque se conserva."""
    block = f"{START}\n{page.body}\n{END}"
    after = "\n"
    if existing and START in existing and END in existing:
        after = existing.split(END, 1)[1]
    return f"{_frontmatter({**page.front, 'generatedBy': 'jarvis-red'})}\n\n{block}{after}"


TREE_ROOTS = (COMPANIES_DIR, NEXUS_DIR, CONTACTS_DIR, AGENDA_DIR, KNOWLEDGE_DIR)


def _generated_ids(vault: Path) -> dict[str, Path]:
    """`id` -> nota, de las notas generadas (o creadas por jarvis_remember) del árbol."""
    found = {}
    for root in (*TREE_ROOTS, "."):
        base = vault / root
        files = base.rglob("*.md") if root != "." else base.glob("*.md")
        for path in files if base.is_dir() else []:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            generated = START in text or _front_value(text, "generatedBy")
            if generated and (page_id := _front_value(text, "id")):
                found.setdefault(page_id, path)
    return found


def _move(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source.replace(target)


def _prune(vault: Path) -> None:
    """Carpetas que se han quedado vacías tras mover notas (las ramas se rehacen solas)."""
    for root in (*TREE_ROOTS, "sources/proyectos"):
        base = vault / root
        if not base.is_dir():
            continue
        for folder in [*sorted((p for p in base.rglob("*") if p.is_dir()), reverse=True), base]:
            if not any(folder.iterdir()):
                folder.rmdir()


def write_tree_index(vault: Path, snap: Snapshot) -> bool:
    """Dónde está la nota y la carpeta de cada empresa y proyecto (para OpenProject y actas)."""
    index = {
        "companies": {
            c: {"note": _company_note(c), "dir": _company_dir(c)} for c in snap.companies
        },
        "projects": {
            p: {
                "note": _project_note(i["company"], p),
                "dir": _project_dir(i["company"], p),
                "company": i["company"],
            }
            for p, i in snap.projects.items()
        },
    }
    target = vault / TREE_INDEX
    content = json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True


def write_pages(vault: Path, pages: list[Page], snap: Snapshot) -> int:
    """Escribe las notas que cambian y mueve las que cambian de sitio. Devuelve cuántas."""
    written = 0
    ids = _generated_ids(vault)
    for page in pages:
        target = vault / f"{page.path}.md"
        if page.acta_from:
            written += _write_acta(vault, page, target)
            continue
        old = ids.get(page.front.get("id", ""))
        if old and old != target and old.exists() and not target.exists():
            _move(old, target)  # cambia de rama: se lleva lo que escribiste en ella
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
    write_tree_index(vault, snap)
    _prune(vault)
    return written


def _write_acta(vault: Path, page: Page, target: Path) -> int:
    """Lleva el acta a su sitio del árbol y le pone (o renueva) el bloque gestionado."""
    source = vault / f"{page.acta_from}.md"
    if source != target:
        if not source.exists() or target.exists():
            return 0
        _move(source, target)
    text = target.read_text(encoding="utf-8")
    block = f"{START}\n{page.body}\n{END}"
    if START in text and END in text:
        new = text.split(START, 1)[0] + block + text.split(END, 1)[1]
    else:
        new = text.rstrip("\n") + "\n\n" + block + "\n"
    if new == text and source == target:
        return 0
    target.write_text(new, encoding="utf-8")
    return 1


def acta_folder(vault: Path, project: str, slug: str) -> Path:
    """Carpeta para un acta nueva: las reuniones de su proyecto en el árbol si la red ya lo
    conoce; si no, `sources/proyectos/<slug>/actas`, y la red la moverá a su sitio."""
    try:
        index = json.loads((vault / TREE_INDEX).read_text(encoding="utf-8"))
        info = index["projects"][project]
    except (OSError, ValueError, KeyError):
        return vault / "sources" / "proyectos" / (slug or "reuniones") / "actas"
    return vault / info["dir"] / PROJECT_GROUPS["reunion"][1]


# --- Memoria escrita por Jarvis --------------------------------------------------------

NOTES_HEADING = "## Notas"
# Empresas, proyectos, personas (y nexos), temas generales y metodologías: sobre eso se
# pueden anotar cosas. Las directivas de Jarvis no: son una copia de su MEMORY.md.
REMEMBER_GLOBS = (
    f"{COMPANIES_DIR}/*/🏢 *.md",
    f"{COMPANIES_DIR}/*/*/📁 *.md",
    f"{COMPANIES_DIR}/*/Equipo/👤 *.md",
    f"{NEXUS_DIR}/🔗 *.md",
    f"{CONTACTS_DIR}/👤 *.md",
    f"{TOPICS_DIR}/💡 *.md",
    f"{METHODOLOGIES_DIR}/*/📐 *.md",
)
NEW_NOTES = {
    "persona": (CONTACTS_DIR, "👤", "entity.persona", "entity"),
    "tema": (TOPICS_DIR, "💡", "concept.tema", "concept"),
    "metodologia": (METHODOLOGIES_DIR, "📐", "concept.metodologia", "concept"),
}


def _rememberable(vault: Path) -> list[Path]:
    return [p for pattern in REMEMBER_GLOBS for p in sorted(vault.glob(pattern))]


def find_note(vault: Path, about: str) -> Path:
    """Nota de un proyecto, empresa, persona o tema por su nombre (sin tildes, mayúsculas
    ni el icono del nombre del archivo)."""
    notes = _rememberable(vault)
    wanted = _key(about)
    for matches in (
        [p for p in notes if _key(p.stem) == wanted],
        [p for p in notes if wanted and wanted in _key(p.stem)],
    ):
        if len(matches) == 1:
            return matches[0]
        if matches:
            names = ", ".join(_key(p.stem) for p in matches)
            raise LookupError(f"«{about}» es ambiguo: {names}.")
    names = ", ".join(p.stem for p in notes) or "ninguna (¿está activa la red de conocimiento?)"
    raise LookupError(
        f"No hay nota de «{about}». Hay: {names}. Para crearla, repite con "
        "new='persona' (una persona), new='tema' (un tema general) o new='metodologia' "
        "(una metodología de trabajo)."
    )


def _new_note(vault: Path, about: str, kind: str) -> Path:
    if kind not in NEW_NOTES:
        raise LookupError(f"new debe ser 'persona', 'tema' o 'metodologia', no «{kind}».")
    name = note_name(about)
    if _key(name) == _key(_label(DIRECTIVES_NOTE)):
        raise LookupError("Las directivas se editan en MEMORY.md, no con jarvis_remember.")
    folder, icon, prefix, page_type = NEW_NOTES[kind]
    if kind == "metodologia":
        folder = f"{folder}/{name}"
        page_id = f"{prefix}.{methodology_id(name)}"
    else:
        page_id = f"{prefix}.{_slug(name)}"
    note = vault / folder / f"{icon} {name}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    # Bloque gestionado y su id: si la red genera después esta nota (o la cambia de rama),
    # rellena el bloque y la mueve sin tocar lo anotado.
    front = _frontmatter({"pageType": page_type, "id": page_id, "title": name})
    note.write_text(f"{front}\n\n{START}\n# {icon} {name}\n{END}\n", encoding="utf-8")
    return note


def remember(
    vault: Path, about: str, text: str, today: datetime.date | None = None, new: str = ""
) -> Path:
    """Añade una nota fechada fuera del bloque generado de la nota de `about`: se conserva
    al regenerar la red, sale en Obsidian y en la wiki de OpenProject. Con `new`
    ("persona", "tema" o "metodologia") crea la nota si aún no existe."""
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
    en cada conversación) en la rama de conocimiento, para verla en Obsidian."""
    source = workspace / "MEMORY.md"
    if not source.is_file():
        return False
    target = vault / f"{DIRECTIVES_NOTE}.md"
    content = (
        f"{_frontmatter({'generatedBy': 'jarvis-directivas', 'tags': ['jarvis', 'directivas']})}"
        f"\n\nRama de {link(BRANCHES['conocimiento'][0])}\n\n"
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


def refresh(vault: Path, workspace: Path | None = None) -> int:
    from packages.openproject.client import OpenProjectClient
    from packages.openproject.config import config_from_env

    config = config_from_env()
    op = OpenProjectClient(config) if config else None
    memory_file = workspace / "MEMORY.md" if workspace else None
    memory = (
        memory_file.read_text(encoding="utf-8") if memory_file and memory_file.is_file() else None
    )
    snap = collect(op, _documents(), vault, os.environ.get("JARVIS_OWNER_NAME", ""), memory)
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
                n = refresh(args.vault, args.workspace)
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
