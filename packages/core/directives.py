"""Directivas de Jarvis por zonas y metodología de cada proyecto, para no mezclarlas.

La fuente es el `MEMORY.md` de Jarvis, que tiene zonas:

    ## General
    ### Reuniones         ← directivas que valen para todo, por tema

    ## Metodologías
    ### Scrum             ← una zona por metodología; se añaden las que hagan falta
    - reglas de trabajo…
    ### PMI
    - …

    ## Proyectos
    - Estudio Delta › App de reservas: Scrum
    - Acme › Migración ERP: PMI + Scrum (híbrido pedido por el propietario)

Los documentos del RAG pueden llevar metodología (`doc_metadata["methodology"]`, payload
`methodology` en Qdrant). Una consulta de un proyecto con metodología solo ve los
documentos de esa metodología y los que no tienen ninguna (packages/rag/store.py).

`set_directive` escribe una sección de una zona sin tocar las demás: es lo que usa Jarvis
(herramientas `jarvis_set_directive`, `jarvis_set_methodology` y
`jarvis_set_project_methodology` de jarvis-rag) en vez de editar el archivo a mano.
"""

import re
from dataclasses import dataclass, field

from packages.core.scope import slugify

METHODS_HEADING = "metodologias"
PROJECTS_HEADING = "proyectos"
# Zona → título de su sección `##` en MEMORY.md.
ZONES = {"general": "General", "metodologia": "Metodologías", "proyecto": "Proyectos"}
MAX_DIRECTIVE_CHARS = 2000
_PROJECT_LINE = re.compile(r"^\s*[-*]\s+(?P<project>[^:]+?)\s*:\s*(?P<methods>.+?)\s*$")
_SEPARATOR = re.compile(r"\s*(?:\+|,|\by\b|\band\b)\s*")


def methodology_id(name: str) -> str:
    """Identificador de una metodología ("Scrum" → "scrum"); vacío si no hay nombre."""
    return slugify(name or "")


def methodology_from_metadata(metadata: dict | None) -> str:
    """Nombre legible guardado en `doc_metadata` (vacío = sin metodología)."""
    return str((metadata or {}).get("methodology") or "").strip()


@dataclass(frozen=True, slots=True)
class Directives:
    # Nombres de las zonas de metodología, en el orden de MEMORY.md.
    methods: list[str] = field(default_factory=list)
    # (empresa, proyecto) normalizados → identificadores de metodología. Sin empresa en
    # la línea, la clave lleva empresa "".
    projects: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    # Misma clave → el proyecto tal como está escrito ("Acme › Migración ERP").
    labels: dict[tuple[str, str], str] = field(default_factory=dict)

    def for_project(self, company: str, project: str) -> list[str]:
        """Metodologías del proyecto (vacío si no tiene): primero con su empresa y, si la
        línea no la nombraba, solo por el nombre del proyecto."""
        if not project:
            return []
        wanted = slugify(project)
        return self.projects.get((slugify(company), wanted)) or self.projects.get(("", wanted), [])


def _heading(line: str, level: int) -> str | None:
    prefix = "#" * level + " "
    if line.startswith(prefix) and not line.startswith(prefix + "#"):
        return line[len(prefix) :].strip()
    return None


def _methods_of(text: str) -> list[str]:
    text = re.sub(r"\(.*?\)", "", text)  # notas entre paréntesis: "(híbrido pedido…)"
    ids = [methodology_id(part) for part in _SEPARATOR.split(text)]
    return list(dict.fromkeys(i for i in ids if i))


def parse_directives(text: str) -> Directives:
    """Zonas de metodología y metodología de cada proyecto según MEMORY.md."""
    methods: list[str] = []
    projects: dict[tuple[str, str], list[str]] = {}
    labels: dict[tuple[str, str], str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if (title := _heading(line, 2)) is not None:
            section = slugify(title)
            continue
        if section == METHODS_HEADING and (name := _heading(line, 3)):
            methods.append(name)
        elif section == PROJECTS_HEADING and (match := _PROJECT_LINE.match(line)):
            company, _, project = match["project"].rpartition("›")
            ids = _methods_of(match["methods"])
            key = (slugify(company), slugify(project))
            if key[1] and ids:
                projects[key] = ids
                labels[key] = match["project"].strip()
    return Directives(methods=methods, projects=projects, labels=labels)


def _zone_bounds(lines: list[str], title: str) -> tuple[int, int]:
    """Primera línea después del título `## <title>` y final de la zona. Si no existe la
    zona, la añade al final."""
    start = next((i + 1 for i, line in enumerate(lines) if _is_heading(line, 2, title)), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(["", f"## {title}", ""])
        start = len(lines)
    end = next((i for i in range(start, len(lines)) if _heading(lines[i], 2) is not None), None)
    return start, len(lines) if end is None else end


def _is_heading(line: str, level: int, name: str) -> bool:
    title = _heading(line.rstrip(), level)
    return title is not None and slugify(title) == slugify(name)


def _project_key(label: str) -> tuple[str, str]:
    company, _, project = label.rpartition("›")
    return slugify(company), slugify(project)


def _insert_at(lines: list[str], start: int, end: int) -> int:
    """Dónde añadir algo al final de una zona: tras su último contenido."""
    while end > start and not lines[end - 1].strip():
        end -= 1
    return end


def _body_lines(body: str) -> list[str]:
    """El texto de la directiva, sin títulos que rompan las zonas (pasan a negrita)."""
    lines = []
    for line in body.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            line = f"**{stripped.lstrip('#').strip()}**"
        lines.append(line.rstrip())
    return lines


def _rule_key(line: str) -> str:
    """Clave de una regla ("- **Sprints:** de dos semanas" → "sprints"), o "" si no tiene."""
    text = line.strip().lstrip("-*").strip().replace("**", "")
    key, colon, _ = text.partition(":")
    return slugify(key) if colon and 0 < len(key.strip()) <= 40 else ""


def _merge_rules(current: list[str], changes: list[str]) -> list[str]:
    """Reglas de una sección con los cambios aplicados: la regla con la misma clave se
    sustituye, lo nuevo se añade y el resto se conserva."""
    merged = list(current)
    while merged and not merged[-1].strip():
        merged.pop()
    for line in changes:
        if not line.strip():
            continue
        key = _rule_key(line)
        same = next((i for i, old in enumerate(merged) if key and _rule_key(old) == key), None)
        if same is not None:
            merged[same] = line
        elif line.strip() not in {old.strip() for old in merged}:
            merged.append(line)
    return merged


def set_directive(
    text: str, zone: str, name: str, body: str, *, replace_all: bool = False
) -> tuple[str, str]:
    """MEMORY.md con la directiva aplicada y la sección tal como queda. Las demás secciones
    no se tocan: un cambio en Scrum nunca pisa PMI ni la metodología de otro proyecto.

    * general / metodologia: sección `### <name>`. Si ya existe, `body` se fusiona regla a
      regla (la de la misma clave, "Sprints: …", se sustituye; el resto se conserva);
      con `replace_all` la sección entera pasa a ser `body`. `body` vacío la quita.
    * proyecto: línea `- <name>: <body>` (`name` = "Empresa › Proyecto", `body` = las
      metodologías: "Scrum", "PMI + Scrum")."""
    zone = slugify(zone).replace("-", "")
    if zone not in ZONES:
        raise ValueError(f"Zona desconocida «{zone}»: usa general, metodologia o proyecto.")
    name = " ".join(name.split())
    if not slugify(name.replace("›", " ")):
        raise ValueError("Falta el nombre de la sección (p. ej. «Scrum» o «Acme › ERP»).")
    body = body.strip()
    if len(body) > MAX_DIRECTIVE_CHARS:
        raise ValueError(
            f"Directiva demasiado larga ({len(body)} caracteres, máximo "
            f"{MAX_DIRECTIVE_CHARS}): resúmela en reglas cortas y deja el detalle en su nota "
            "del vault (jarvis_remember)."
        )
    lines = text.splitlines()
    start, end = _zone_bounds(lines, ZONES[zone])
    if zone == "proyecto":
        if body and not _methods_of(body):
            raise ValueError("Indica la metodología del proyecto (p. ej. «Scrum»).")
        key = _project_key(name)
        old = [
            i
            for i in range(start, end)
            if (m := _PROJECT_LINE.match(lines[i])) and _project_key(m["project"]) == key
        ]
        if old and (m := _PROJECT_LINE.match(lines[old[0]])):
            name = m["project"].strip()  # se conserva el nombre tal como estaba escrito
        new = [f"- {name}: {' '.join(body.split())}"] if body else []
    else:
        first = next((i for i in range(start, end) if _is_heading(lines[i], 3, name)), None)
        old = []
        if first is not None:
            name = _heading(lines[first], 3) or name  # se conserva el título que ya tenía
            last = next(
                (i for i in range(first + 1, end) if _heading(lines[i], 3) is not None), end
            )
            old = list(range(first, _insert_at(lines, first, last)))
        rules = _body_lines(body)
        if old and body and not replace_all:
            rules = _merge_rules(lines[old[0] + 1 : old[-1] + 1], rules)
        new = [f"### {name}", *rules] if body else []
    if old:
        lines[old[0] : old[-1] + 1] = new
    elif new:
        at = _insert_at(lines, start, end)
        spacer = [""] if zone != "proyecto" or not lines[at - 1].lstrip().startswith("-") else []
        lines[at:at] = [*spacer, *new]
    result = "\n".join(lines).rstrip() + "\n"
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"([^\n])\n(## )", r"\1\n\n\2", result)
    return result, "\n".join(new)
