"""Cliente mínimo de la API v3 de OpenProject para el servidor MCP `jarvis-pm`.

Solo lo que Jarvis necesita para llevar el seguimiento de proyectos desde Telegram:
proyectos (una empresa es un proyecto padre y sus proyectos cuelgan de ella), paquetes
de trabajo (tareas, hitos, riesgos...), comentarios y un resumen de estado. Los nombres
que usa el modelo (proyecto, tipo, estado, persona) se resuelven aquí a los enlaces que
pide la API, para que las herramientas MCP reciban texto normal.

Autenticación: clave de API de un usuario de OpenProject (Basic `apikey:<clave>`).
"""

import datetime
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import httpx

from packages.core.errors import NotFoundError, ProviderUnavailableError, ValidationFailedError

_TIMEOUT_SECONDS = 30
_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class OpenProjectConfig:
    # URL por la que habla Jarvis (dentro del servidor) y la que abre el usuario en el
    # navegador (por Tailscale); si no hay pública se usa la interna.
    url: str
    api_key: str
    public_url: str = ""
    # Usuario humano que entra como administrador en cada proyecto nuevo, para poder
    # asignarle trabajo por nombre (la API solo asigna a miembros del proyecto).
    owner_login: str = "admin"

    @property
    def web_url(self) -> str:
        return (self.public_url or self.url).rstrip("/")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def slugify(text: str) -> str:
    """Identificador de proyecto válido en OpenProject (minúsculas, cifras y guiones)."""
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize(text)).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"p-{slug}".strip("-")
    return slug[:100]


def _id_from_href(href: str | None) -> int | None:
    if not href:
        return None
    tail = href.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def _raw(value: dict | None) -> str:
    return (value or {}).get("raw") or ""


class OpenProjectClient:
    def __init__(self, config: OpenProjectConfig, *, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._http = httpx.Client(
            base_url=config.url.rstrip("/") + "/api/v3",
            auth=("apikey", config.api_key),
            # Detrás de Tailscale OpenProject corre con HTTPS=true y redirige lo que llegue
            # por HTTP; desde dentro del servidor se le habla por HTTP diciendo que es HTTPS.
            headers={"Content-Type": "application/json", "X-Forwarded-Proto": "https"},
            timeout=_TIMEOUT_SECONDS,
            transport=transport,
        )

    # --- HTTP ---------------------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"OpenProject no responde: {exc}") from exc
        if response.status_code == 404:
            raise NotFoundError("No existe en OpenProject.")
        if response.status_code in (401, 403):
            raise ProviderUnavailableError(
                "OpenProject rechazó la clave de API de Jarvis (¿se regeneró el volumen?)."
            )
        if response.status_code >= 400:
            raise ValidationFailedError(self._error_message(response))
        return response.json() if response.content else {}

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"OpenProject respondió {response.status_code}."
        errors = data.get("_embedded", {}).get("errors")
        if errors:
            return " ".join(e.get("message", "") for e in errors).strip()
        return data.get("message") or f"OpenProject respondió {response.status_code}."

    def _elements(self, path: str, params: dict | None = None) -> list[dict]:
        query = {"pageSize": _PAGE_SIZE, **(params or {})}
        return self._request("GET", path, params=query).get("_embedded", {}).get("elements", [])

    # --- Catálogos (tipos, estados, prioridades, personas) ------------------------------

    def _match(self, elements: list[dict], name: str, what: str, key: str = "name") -> dict:
        wanted = _normalize(name)
        for element in elements:
            if _normalize(str(element.get(key, ""))) == wanted:
                return element
        for element in elements:
            if wanted and wanted in _normalize(str(element.get(key, ""))):
                return element
        options = ", ".join(str(e.get(key)) for e in elements)
        raise ValidationFailedError(f"{what} «{name}» no existe. Opciones: {options}.")

    def types(self, project_id: int | None = None) -> list[dict]:
        path = f"/projects/{project_id}/types" if project_id else "/types"
        return self._elements(path)

    def statuses(self) -> list[dict]:
        return self._elements("/statuses")

    def priorities(self) -> list[dict]:
        return self._elements("/priorities")

    def assignees(self, project_id: int) -> list[dict]:
        return self._elements(f"/projects/{project_id}/available_assignees")

    # --- Proyectos ----------------------------------------------------------------------

    def projects(self) -> list[dict]:
        return self._elements("/projects", {"sortBy": json.dumps([["name", "asc"]])})

    def find_project(self, name: str) -> dict:
        projects = self.projects()
        for key in ("identifier", "name"):
            for project in projects:
                if _normalize(str(project.get(key, ""))) == _normalize(name):
                    return project
        return self._match(projects, name, "El proyecto")

    def create_project(self, name: str, *, parent: str = "", description: str = "") -> dict:
        body: dict[str, Any] = {
            "name": name,
            "identifier": slugify(name),
            "description": {"raw": description},
        }
        if parent:
            parent_project = self.find_project(parent)
            body["_links"] = {"parent": {"href": f"/api/v3/projects/{parent_project['id']}"}}
        project = self._request("POST", "/projects", json=body)
        self._add_owner(project)
        return project

    def _add_owner(self, project: dict) -> None:
        if not self.config.owner_login:
            return
        users = self._elements(
            "/users",
            {
                "filters": json.dumps(
                    [{"login": {"operator": "=", "values": [self.config.owner_login]}}]
                )
            },
        )
        if not users:
            return
        role = self._match(self._elements("/roles"), "Administrador de proyecto", "El rol")
        self._request(
            "POST",
            "/memberships",
            params={"notify": "false"},
            json={
                "_links": {
                    "project": {"href": f"/api/v3/projects/{project['id']}"},
                    "principal": {"href": users[0]["_links"]["self"]["href"]},
                    "roles": [{"href": role["_links"]["self"]["href"]}],
                }
            },
        )

    def project_url(self, project: dict, view: str = "") -> str:
        base = f"{self.config.web_url}/projects/{project['identifier']}"
        return f"{base}/{view}" if view else base

    # --- Paquetes de trabajo ------------------------------------------------------------

    def work_packages(
        self,
        project: dict,
        *,
        only_open: bool = True,
        type_name: str = "",
        due_within_days: int | None = None,
        overdue: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        filters: list[dict] = []
        if only_open or overdue:
            filters.append({"status": {"operator": "o", "values": []}})
        if type_name:
            wp_type = self._match(self.types(project["id"]), type_name, "El tipo")
            filters.append({"type": {"operator": "=", "values": [str(wp_type["id"])]}})
        if overdue:
            filters.append({"dueDate": {"operator": "<t-", "values": ["1"]}})
        elif due_within_days is not None:
            filters.append({"dueDate": {"operator": "<t+", "values": [str(due_within_days)]}})
        params = {
            "filters": json.dumps(filters),
            "sortBy": json.dumps([["dueDate", "asc"], ["id", "asc"]]),
            "pageSize": limit,
        }
        return self._elements(f"/projects/{project['id']}/work_packages", params)

    def work_package(self, wp_id: int) -> dict:
        return self._request("GET", f"/work_packages/{wp_id}")

    def create_work_package(
        self,
        project: dict,
        subject: str,
        *,
        type_name: str = "Tarea",
        description: str = "",
        start_date: str = "",
        due_date: str = "",
        assignee: str = "",
        priority: str = "",
    ) -> dict:
        wp_type = self._match(self.types(project["id"]), type_name, "El tipo")
        links: dict[str, Any] = {"type": {"href": wp_type["_links"]["self"]["href"]}}
        if assignee:
            person = self._match(self.assignees(project["id"]), assignee, "La persona")
            links["assignee"] = {"href": person["_links"]["self"]["href"]}
        if priority:
            prio = self._match(self.priorities(), priority, "La prioridad")
            links["priority"] = {"href": prio["_links"]["self"]["href"]}
        body: dict[str, Any] = {
            "subject": subject,
            "description": {"raw": description},
            "_links": links,
        }
        if wp_type.get("isMilestone"):
            # Los hitos tienen una sola fecha.
            if due_date or start_date:
                body["date"] = _check_date(due_date or start_date)
        else:
            if start_date:
                body["startDate"] = _check_date(start_date)
            if due_date:
                body["dueDate"] = _check_date(due_date)
        return self._request(
            "POST",
            f"/projects/{project['id']}/work_packages",
            params={"notify": "false"},
            json=body,
        )

    def update_work_package(
        self,
        wp_id: int,
        *,
        status: str = "",
        subject: str = "",
        percent_done: int | None = None,
        start_date: str = "",
        due_date: str = "",
        assignee: str = "",
        comment: str = "",
    ) -> dict:
        current = self.work_package(wp_id)
        body: dict[str, Any] = {"lockVersion": current["lockVersion"], "_links": {}}
        if subject.strip():
            body["subject"] = subject.strip()
        if status:
            new_status = self._match(self.statuses(), status, "El estado")
            body["_links"]["status"] = {"href": new_status["_links"]["self"]["href"]}
        if percent_done is not None:
            if not 0 <= percent_done <= 100:
                raise ValidationFailedError("El porcentaje debe estar entre 0 y 100.")
            body["percentageDone"] = percent_done
        milestone = "date" in current and "dueDate" not in current
        if due_date:
            body["date" if milestone else "dueDate"] = _check_date(due_date)
        if start_date and not milestone:
            body["startDate"] = _check_date(start_date)
        if assignee:
            project_id = _id_from_href(current["_links"]["project"]["href"])
            if project_id is None:
                raise ValidationFailedError(f"No se encuentra el proyecto de la #{wp_id}.")
            person = self._match(self.assignees(project_id), assignee, "La persona")
            body["_links"]["assignee"] = {"href": person["_links"]["self"]["href"]}
        updated = current
        if len(body) > 2 or body["_links"]:
            updated = self._request(
                "PATCH", f"/work_packages/{wp_id}", params={"notify": "false"}, json=body
            )
        if comment:
            self.add_comment(wp_id, comment)
        return updated

    def add_comment(self, wp_id: int, text: str) -> None:
        self._request(
            "POST",
            f"/work_packages/{wp_id}/activities",
            params={"notify": "false"},
            json={"comment": {"raw": text}},
        )

    def work_package_url(self, wp: dict) -> str:
        return f"{self.config.web_url}/work_packages/{wp['id']}"

    # --- Seguimiento y control ----------------------------------------------------------

    def status_report(self, project: dict, *, today: datetime.date | None = None) -> dict:
        """Cifras para el informe de seguimiento: abiertos por estado y tipo, vencidos,
        próximos 7 días, hitos pendientes y riesgos abiertos."""
        today = today or datetime.date.today()
        open_wps = self.work_packages(project, only_open=True, limit=_PAGE_SIZE)
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        overdue, upcoming, milestones, risks = [], [], [], []
        for wp in open_wps:
            links = wp["_links"]
            status = links["status"]["title"]
            wp_type = links["type"]["title"]
            by_status[status] = by_status.get(status, 0) + 1
            by_type[wp_type] = by_type.get(wp_type, 0) + 1
            due = wp.get("dueDate") or wp.get("date")
            if due:
                due_date = datetime.date.fromisoformat(due)
                if due_date < today:
                    overdue.append(wp)
                elif (due_date - today).days <= 7:
                    upcoming.append(wp)
            if _normalize(wp_type) in ("milestone", "hito"):
                milestones.append(wp)
            if _normalize(wp_type) in ("riesgo", "risk"):
                risks.append(wp)
        return {
            "open_total": len(open_wps),
            "by_status": by_status,
            "by_type": by_type,
            "overdue": overdue,
            "upcoming": upcoming,
            "milestones": milestones,
            "risks": risks,
        }


def _check_date(value: str) -> str:
    try:
        return datetime.date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError as exc:
        raise ValidationFailedError(f"Fecha no válida «{value}»: usa AAAA-MM-DD.") from exc


def describe_work_package(wp: dict) -> str:
    """Una línea legible para Telegram."""
    links = wp["_links"]
    parts = [f"#{wp['id']} [{links['type']['title']}] {wp['subject']}", links["status"]["title"]]
    due = wp.get("dueDate") or wp.get("date")
    if wp.get("startDate") and wp.get("dueDate"):
        parts.append(f"del {wp['startDate']} al {wp['dueDate']}")
    elif due:
        parts.append(f"vence {due}")
    if links.get("assignee", {}).get("title"):
        parts.append(links["assignee"]["title"])
    if wp.get("percentageDone"):
        parts.append(f"{wp['percentageDone']}%")
    return " · ".join(parts)


def description_of(wp: dict) -> str:
    return _raw(wp.get("description"))
