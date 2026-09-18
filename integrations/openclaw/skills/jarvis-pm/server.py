"""Servidor MCP `jarvis-pm`: gestión de proyectos en OpenProject desde Telegram.

Pocas herramientas y con parámetros de texto normal (nombres de proyecto, tipo, estado,
persona) para que el modelo local las elija bien; la traducción a la API v3 vive en
`packages/openproject`. No hay herramientas de borrado: eso se hace en la web.
"""

import functools
import os
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from packages.core.errors import JarvisError, ValidationFailedError  # noqa: E402
from packages.openproject.client import (  # noqa: E402
    OpenProjectClient,
    OpenProjectConfig,
    describe_work_package,
)

RUNTIME_DIR = Path(os.environ.get("JARVIS_RUNTIME_DIR", "/run/jarvis"))

mcp = FastMCP("jarvis-pm")


def _api_key() -> str:
    key = os.environ.get("OPENPROJECT_API_KEY", "")
    if not key and (RUNTIME_DIR / "openproject_api_key").is_file():
        key = (RUNTIME_DIR / "openproject_api_key").read_text().strip()
    return key


def _public_url() -> str:
    """URL para abrir en el navegador: por Tailscale si el servidor está en el tailnet."""
    url = os.environ.get("OPENPROJECT_PUBLIC_URL", "")
    dnsname = Path("/var/run/tailscale/dnsname")
    if not url and dnsname.is_file() and dnsname.read_text().strip():
        port = os.environ.get("OPENPROJECT_HTTPS_PORT", "8445")
        url = f"https://{dnsname.read_text().strip()}:{port}"
    return url


_client: OpenProjectClient | None = None


def _op() -> OpenProjectClient:
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            raise JarvisError(
                "OpenProject no está configurado: activa el perfil `pm` en el servidor "
                "(COMPOSE_PROFILES) y reinicia (docs/OPENPROJECT.md)."
            )
        _client = OpenProjectClient(
            OpenProjectConfig(
                url=os.environ.get("OPENPROJECT_URL", "http://127.0.0.1:8090"),
                api_key=key,
                public_url=_public_url(),
                owner_login=os.environ.get("OPENPROJECT_OWNER_LOGIN", "admin"),
            )
        )
    return _client


def _safe(fn):
    """Errores de OpenProject como texto para el chat, no como excepción."""

    # functools.wraps conserva la firma: FastMCP la usa para el esquema de parámetros.
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except JarvisError as exc:
            return f"No se pudo: {exc.message}"

    return wrapper


@mcp.tool()
@_safe
def pm_projects() -> str:
    """Lista las empresas y proyectos de OpenProject (los proyectos cuelgan de su empresa)."""
    op = _op()
    projects = op.projects()
    if not projects:
        return "No hay proyectos todavía."
    names = {p["id"]: p["name"] for p in projects}
    lines = []
    for p in projects:
        parent = (p["_links"].get("parent") or {}).get("href")
        parent_name = names.get(int(parent.rsplit("/", 1)[-1])) if parent else None
        prefix = f"{parent_name} › " if parent_name else ""
        lines.append(f"- {prefix}{p['name']} ({op.project_url(p)})")
    return "\n".join(lines)


@mcp.tool()
@_safe
def pm_create_project(name: str, company: str = "", description: str = "") -> str:
    """Crea un proyecto. Si se indica `company` (empresa ya existente), el proyecto cuelga
    de ella; sin `company` se crea en la raíz (úsalo para dar de alta una empresa)."""
    op = _op()
    project = op.create_project(name, parent=company, description=description)
    return f"Creado «{project['name']}»: {op.project_url(project)}"


@mcp.tool()
@_safe
def pm_list_tasks(
    project: str,
    kind: str = "",
    include_closed: bool = False,
    due_within_days: int = -1,
    overdue_only: bool = False,
) -> str:
    """Lista paquetes de trabajo de un proyecto, ordenados por fecha de vencimiento.
    `kind` filtra por tipo (Tarea, Hito, Riesgo...). `due_within_days` >= 0 limita a
    los que vencen en esos días; `overdue_only` solo los vencidos."""
    op = _op()
    proj = op.find_project(project)
    wps = op.work_packages(
        proj,
        only_open=not include_closed,
        type_name=kind,
        due_within_days=due_within_days if due_within_days >= 0 else None,
        overdue=overdue_only,
    )
    if not wps:
        return f"Nada que mostrar en «{proj['name']}» con ese filtro."
    lines = [describe_work_package(wp) for wp in wps]
    lines.append(f"Tablero: {op.project_url(proj, 'work_packages')}")
    return "\n".join(lines)


@mcp.tool()
@_safe
def pm_create_task(
    project: str,
    subject: str,
    kind: str = "Tarea",
    description: str = "",
    start_date: str = "",
    due_date: str = "",
    assignee: str = "",
    priority: str = "",
) -> str:
    """Crea un paquete de trabajo en un proyecto. `kind`: Tarea, Hito o Riesgo (u otro
    tipo activo en el proyecto). Fechas en AAAA-MM-DD. `assignee` es el nombre de una persona
    del proyecto. Para un riesgo, pon en `description` probabilidad, impacto y mitigación."""
    op = _op()
    proj = op.find_project(project)
    wp = op.create_work_package(
        proj,
        subject,
        type_name=kind,
        description=description,
        start_date=start_date,
        due_date=due_date,
        assignee=assignee,
        priority=priority,
    )
    return f"Creado {describe_work_package(wp)}\n{op.work_package_url(wp)}"


@mcp.tool()
@_safe
def pm_update_task(
    task_id: int,
    status: str = "",
    percent_done: int = -1,
    due_date: str = "",
    assignee: str = "",
    comment: str = "",
) -> str:
    """Actualiza un paquete de trabajo por su número (#id): estado (Nuevo, En curso,
    Cerrado...), porcentaje hecho (0-100), fecha de vencimiento, responsable y/o un
    comentario. Solo cambia lo que se indique."""
    op = _op()
    wp = op.update_work_package(
        task_id,
        status=status,
        percent_done=percent_done if percent_done >= 0 else None,
        due_date=due_date,
        assignee=assignee,
        comment=comment,
    )
    return f"Actualizado {describe_work_package(wp)}\n{op.work_package_url(wp)}"


@mcp.tool()
@_safe
def pm_status_report(project: str) -> str:
    """Informe de seguimiento y control de un proyecto: trabajo abierto por estado y tipo,
    vencidos, lo que vence en 7 días, hitos pendientes y riesgos abiertos."""
    op = _op()
    proj = op.find_project(project)
    r = op.status_report(proj)

    def block(title: str, wps: list[dict]) -> list[str]:
        if not wps:
            return [f"{title}: ninguno"]
        return [f"{title} ({len(wps)}):", *(f"  {describe_work_package(wp)}" for wp in wps[:10])]

    lines = [
        f"Proyecto «{proj['name']}»: {r['open_total']} abiertos",
        "Por estado: " + (", ".join(f"{k} {v}" for k, v in r["by_status"].items()) or "—"),
        "Por tipo: " + (", ".join(f"{k} {v}" for k, v in r["by_type"].items()) or "—"),
        *block("⚠️ Vencidos", r["overdue"]),
        *block("Próximos 7 días", r["upcoming"]),
        *block("Hitos pendientes", r["milestones"]),
        *block("Riesgos abiertos", r["risks"]),
        f"Gantt: {op.project_url(proj, 'gantt')}",
        f"Tableros: {op.project_url(proj, 'boards')}",
    ]
    return "\n".join(lines)


def _minutes(job_id: str) -> dict:
    """Resultado de un trabajo de acta de la API de Jarvis (jarvis_meeting_minutes)."""
    api = httpx.Client(
        base_url=os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000"),
        headers={"Authorization": f"Bearer {os.environ.get('JARVIS_API_INTERNAL_TOKEN', '')}"},
        timeout=30,
    )
    with api:
        response = api.get(f"/v1/jobs/{job_id}")
    if response.status_code == 404:
        raise ValidationFailedError(f"No existe el trabajo de acta {job_id}.")
    response.raise_for_status()
    job = response.json()
    if job.get("job_type") != "meeting_minutes" or job.get("status") != "completed":
        raise ValidationFailedError(f"El trabajo {job_id} no es un acta terminada.")
    return job["result"]["minutes"]


@mcp.tool()
@_safe
def pm_import_minutes(project: str, job_id: str) -> str:
    """Crea en OpenProject las acciones (como Tareas) y los riesgos (como Riesgos) de un
    acta de reunión hecha con jarvis_meeting_minutes. Llámala solo cuando el usuario haya
    dicho que sí a crearlas. Si el responsable no es miembro del proyecto, se anota en la
    descripción en vez de asignarlo."""
    op = _op()
    proj = op.find_project(project)
    m = _minutes(job_id)
    origin = f"Origen: acta «{m['titulo']}» ({m['fecha']})."
    created, notes = [], []

    def create(subject: str, kind: str, description: str, due: str, who: str) -> None:
        try:
            wp = op.create_work_package(
                proj, subject, type_name=kind, description=description, due_date=due, assignee=who
            )
        except ValidationFailedError as exc:
            if not who or "persona" not in exc.message:
                raise
            notes.append(f"«{who}» no es miembro de {proj['name']}: queda sin asignar.")
            wp = op.create_work_package(
                proj,
                subject,
                type_name=kind,
                description=f"{description}\nResponsable: {who}",
                due_date=due,
            )
        created.append(describe_work_package(wp))

    for a in m.get("acciones", []):
        detail = "\n".join(x for x in (a.get("detalle", ""), origin) if x)
        create(a["tarea"], "Tarea", detail, a.get("fecha_limite", ""), a.get("responsable", ""))
    for r in m.get("riesgos", []):
        detail = (
            f"Probabilidad: {r.get('probabilidad') or '?'}. Impacto: {r.get('impacto') or '?'}.\n"
            f"Mitigación: {r.get('mitigacion') or '—'}\n{origin}"
        )
        create(r["riesgo"], "Riesgo", detail, "", r.get("responsable", ""))

    if not created:
        return "El acta no tiene acciones ni riesgos que crear."
    lines = [f"Creados en «{proj['name']}» ({len(created)}):", *created, *notes]
    lines.append(f"Tablero: {op.project_url(proj, 'work_packages')}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
