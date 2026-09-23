import datetime
import json

import httpx
import pytest

from packages.core.errors import NotFoundError, ProviderUnavailableError, ValidationFailedError
from packages.openproject.client import (
    OpenProjectClient,
    OpenProjectConfig,
    describe_work_package,
    slugify,
)

CONFIG = OpenProjectConfig(
    url="http://127.0.0.1:8090",
    api_key="clave",
    public_url="https://jarvis.example.ts.net:8445",
)


def _link(kind: str, id_: int, title: str = "") -> dict:
    return {"href": f"/api/v3/{kind}/{id_}", "title": title}


def _collection(elements: list[dict]) -> dict:
    return {"_embedded": {"elements": elements}}


PROJECTS = [
    {
        "id": 1,
        "identifier": "acme",
        "name": "Acme Consulting",
        "_links": {"parent": {"href": None}},
    },
    {
        "id": 2,
        "identifier": "migracion-erp",
        "name": "Migración ERP",
        "_links": {"parent": _link("projects", 1, "Acme Consulting")},
    },
]
TYPES = [
    {"id": 1, "name": "Tarea", "isMilestone": False, "_links": {"self": _link("types", 1)}},
    {"id": 2, "name": "Hito", "isMilestone": True, "_links": {"self": _link("types", 2)}},
    {"id": 7, "name": "Riesgo", "isMilestone": False, "_links": {"self": _link("types", 7)}},
]
STATUSES = [
    {"id": 1, "name": "Nuevo", "_links": {"self": _link("statuses", 1)}},
    {"id": 7, "name": "En curso", "_links": {"self": _link("statuses", 7)}},
    {"id": 12, "name": "Cerrado", "_links": {"self": _link("statuses", 12)}},
]


def _wp(id_: int, subject: str, type_title: str, status: str = "Nuevo", **extra) -> dict:
    return {
        "id": id_,
        "subject": subject,
        "lockVersion": 3,
        "_links": {
            "type": {"title": type_title},
            "status": {"title": status},
            "project": _link("projects", 2),
            "assignee": {"href": None},
        },
        **extra,
    }


class FakeOpenProject:
    """Responde como la API v3 y guarda las peticiones para comprobarlas."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.work_packages: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, method = request.url.path.removeprefix("/api/v3"), request.method
        if request.headers.get("authorization") != "Basic YXBpa2V5OmNsYXZl":
            return httpx.Response(401)
        if (method, path) == ("GET", "/projects"):
            return httpx.Response(200, json=_collection(PROJECTS))
        if (method, path) == ("POST", "/projects"):
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": 3, **body})
        if (method, path) == ("GET", "/users"):
            return httpx.Response(200, json=_collection([{"_links": {"self": _link("users", 4)}}]))
        if (method, path) == ("GET", "/roles"):
            role = {"name": "Administrador de proyecto", "_links": {"self": _link("roles", 5)}}
            return httpx.Response(200, json=_collection([role]))
        if (method, path) == ("POST", "/memberships"):
            return httpx.Response(201, json={})
        if path.endswith("/types"):
            return httpx.Response(200, json=_collection(TYPES))
        if (method, path) == ("GET", "/statuses"):
            return httpx.Response(200, json=_collection(STATUSES))
        if path == "/projects/2/available_assignees":
            ana = {"name": "Ana Pérez", "_links": {"self": _link("users", 9)}}
            return httpx.Response(200, json=_collection([ana]))
        if (method, path) == ("GET", "/projects/2/work_packages"):
            return httpx.Response(200, json=_collection(self.work_packages))
        if (method, path) == ("POST", "/projects/2/work_packages"):
            body = json.loads(request.content)
            wp = _wp(50, body["subject"], "Riesgo")
            return httpx.Response(201, json={**wp, **body})
        if (method, path) == ("GET", "/work_packages/50"):
            return httpx.Response(200, json=_wp(50, "Kick-off", "Tarea", dueDate="2026-09-10"))
        if (method, path) == ("PATCH", "/work_packages/50"):
            return httpx.Response(200, json=_wp(50, "Kick-off", "Tarea", status="En curso"))
        if (method, path) == ("POST", "/work_packages/50/activities"):
            return httpx.Response(201, json={})
        if path == "/work_packages/404":
            return httpx.Response(404, json={"message": "no"})
        return httpx.Response(500)

    def body(self, method: str, path: str) -> dict:
        for request in self.requests:
            if request.method == method and request.url.path == f"/api/v3{path}":
                return json.loads(request.content)
        raise AssertionError(f"no hubo {method} {path}")


@pytest.fixture
def fake() -> FakeOpenProject:
    return FakeOpenProject()


@pytest.fixture
def op(fake: FakeOpenProject) -> OpenProjectClient:
    return OpenProjectClient(CONFIG, transport=httpx.MockTransport(fake))


def test_slugify_generates_valid_identifiers():
    assert slugify("Migración ERP 2026") == "migracion-erp-2026"
    assert slugify("2026 plan") == "p-2026-plan"


def test_find_project_ignores_accents_and_case(op):
    assert op.find_project("migracion erp")["id"] == 2
    assert op.find_project("acme")["id"] == 1


def test_find_project_accepts_company_label(op):
    assert op.find_project("Acme Consulting › Migración ERP")["id"] == 2
    with pytest.raises(ValidationFailedError):
        op.find_project("Otra › Inexistente")


def test_find_project_unknown_lists_options(op):
    with pytest.raises(ValidationFailedError, match="Acme Consulting, Migración ERP"):
        op.find_project("Otro")


def test_create_project_under_company_adds_owner(op, fake):
    project = op.create_project("Portal clientes", parent="Acme Consulting")
    body = fake.body("POST", "/projects")
    assert body["identifier"] == "portal-clientes"
    assert body["_links"]["parent"]["href"] == "/api/v3/projects/1"
    membership = fake.body("POST", "/memberships")["_links"]
    assert membership["project"]["href"] == "/api/v3/projects/3"
    assert membership["principal"]["href"] == "/api/v3/users/4"
    assert membership["roles"] == [{"href": "/api/v3/roles/5"}]
    assert op.project_url(project, "gantt") == (
        "https://jarvis.example.ts.net:8445/projects/portal-clientes/gantt"
    )


def test_create_risk_resolves_names(op, fake):
    project = op.find_project("Migración ERP")
    op.create_work_package(
        project, "Proveedor tarde", type_name="riesgo", due_date="2026-10-15", assignee="ana"
    )
    body = fake.body("POST", "/projects/2/work_packages")
    assert body["_links"]["type"]["href"] == "/api/v3/types/7"
    assert body["_links"]["assignee"]["href"] == "/api/v3/users/9"
    assert body["dueDate"] == "2026-10-15"


def test_milestone_uses_single_date(op, fake):
    op.create_work_package(
        op.find_project("Migración ERP"), "Go-live", type_name="Hito", due_date="2026-12-01"
    )
    body = fake.body("POST", "/projects/2/work_packages")
    assert body["date"] == "2026-12-01"
    assert "dueDate" not in body


def test_invalid_date_is_rejected(op):
    with pytest.raises(ValidationFailedError, match="AAAA-MM-DD"):
        op.create_work_package(op.find_project("Migración ERP"), "x", due_date="el viernes")


def test_update_sends_lock_version_status_and_comment(op, fake):
    op.update_work_package(50, status="en curso", percent_done=40, comment="Arrancado")
    body = fake.body("PATCH", "/work_packages/50")
    assert body["lockVersion"] == 3
    assert body["_links"]["status"]["href"] == "/api/v3/statuses/7"
    assert body["percentageDone"] == 40
    assert fake.body("POST", "/work_packages/50/activities") == {"comment": {"raw": "Arrancado"}}


def test_update_rejects_percentage_out_of_range(op):
    with pytest.raises(ValidationFailedError):
        op.update_work_package(50, percent_done=150)


def test_work_package_filters(op, fake):
    op.work_packages(op.find_project("Migración ERP"), overdue=True)
    request = fake.requests[-1]
    filters = json.loads(request.url.params["filters"])
    assert {"status": {"operator": "o", "values": []}} in filters
    assert {"dueDate": {"operator": "<t-", "values": ["1"]}} in filters
    assert request.headers["x-forwarded-proto"] == "https"


def test_status_report_classifies_work(op, fake):
    fake.work_packages = [
        _wp(1, "Atrasada", "Tarea", dueDate="2026-09-01"),
        _wp(2, "Pronto", "Tarea", status="En curso", dueDate="2026-09-20"),
        _wp(3, "Go-live", "Hito", date="2026-12-01"),
        _wp(4, "Proveedor", "Riesgo"),
    ]
    report = op.status_report(op.find_project("Migración ERP"), today=datetime.date(2026, 9, 18))
    assert report["open_total"] == 4
    assert [wp["id"] for wp in report["overdue"]] == [1]
    assert [wp["id"] for wp in report["upcoming"]] == [2]
    assert [wp["id"] for wp in report["milestones"]] == [3]
    assert [wp["id"] for wp in report["risks"]] == [4]
    assert report["by_status"] == {"Nuevo": 3, "En curso": 1}


def test_errors_are_translated(fake):
    bad_key = OpenProjectClient(
        OpenProjectConfig(url=CONFIG.url, api_key="otra"), transport=httpx.MockTransport(fake)
    )
    with pytest.raises(ProviderUnavailableError, match="clave de API"):
        bad_key.projects()
    good = OpenProjectClient(CONFIG, transport=httpx.MockTransport(fake))
    with pytest.raises(NotFoundError):
        good.work_package(404)


def test_describe_work_package():
    wp = _wp(7, "Kick-off", "Tarea", status="En curso", dueDate="2026-09-10", percentageDone=40)
    wp["_links"]["assignee"] = {"title": "Ana Pérez"}
    assert describe_work_package(wp) == (
        "#7 [Tarea] Kick-off · En curso · vence 2026-09-10 · Ana Pérez · 40%"
    )


def test_update_sets_start_date(op, fake):
    op.update_work_package(50, start_date="2026-09-21", due_date="2026-09-23")
    body = fake.body("PATCH", "/work_packages/50")
    assert body["startDate"] == "2026-09-21" and body["dueDate"] == "2026-09-23"


def test_describe_shows_period():
    wp = _wp(8, "Maquetación", "Tarea", startDate="2026-09-21", dueDate="2026-09-23")
    assert "del 2026-09-21 al 2026-09-23" in describe_work_package(wp)


def test_update_changes_subject(op, fake):
    op.update_work_package(50, subject="  Contratar laespiga.es ")
    assert fake.body("PATCH", "/work_packages/50")["subject"] == "Contratar laespiga.es"
