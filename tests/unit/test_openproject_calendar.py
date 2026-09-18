import asyncio
import datetime
import json

import httpx
import pytest

from apps.api.jarvis_api.adapters.calendar_backends import calendar_backend_from_settings
from packages.core.errors import ProviderUnavailableError
from packages.core.settings import Settings
from packages.openproject import calendar as op_calendar
from packages.openproject.client import OpenProjectClient, OpenProjectConfig

CONFIG = OpenProjectConfig(
    url="http://127.0.0.1:8090", api_key="clave", public_url="https://jarvis.ts.net:8445"
)
TZ = "Europe/Madrid"


def _link(kind: str, id_: int, title: str = "") -> dict:
    return {"href": f"/api/v3/{kind}/{id_}", "title": title}


def _collection(elements: list[dict]) -> dict:
    return {"_embedded": {"elements": elements}}


def _user(id_: int, login: str, email: str) -> dict:
    return {"id": id_, "login": login, "email": email, "status": "active",
            "_links": {"self": _link("users", id_, login)}}  # fmt: skip


USERS = [
    _user(4, "admin", "romen@example.com"),
    _user(5, "jarvis", "jarvis@jarvis.invalid"),
    _user(9, "ana", "ana@example.com"),
]
PROJECTS = [
    {"id": 6, "identifier": "web-corporativa", "name": "Web corporativa", "_links": {}},
    {"id": 7, "identifier": "agenda", "name": "Agenda", "_links": {}},
]


def _meeting(id_: int, start: str, end: str, **extra) -> dict:
    return {
        "id": id_,
        "title": f"Reunión {id_}",
        "startTime": start,
        "endTime": end,
        "template": False,
        "lockVersion": 0,
        "_links": {
            "project": _link("projects", 6, "Web corporativa"),
            "author": _link("users", 5, "Jarvis (asistente)"),
            "participants": [_link("users", 5, "Jarvis (asistente)")],
        },
        **extra,
    }


class FakeOpenProject:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict]] = []
        self.meetings = [
            _meeting(1, "2026-09-21T08:00:00.000Z", "2026-09-21T09:00:00.000Z"),
            _meeting(2, "2026-10-30T08:00:00.000Z", "2026-10-30T09:00:00.000Z"),
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/api/v3"), request.method
        body = json.loads(request.content) if request.content else {}
        self.requests.append((method, path, body))
        if (method, path) == ("GET", "/users"):
            if "login" in request.url.params.get("filters", ""):
                return httpx.Response(200, json=_collection([USERS[0]]))
            return httpx.Response(200, json=_collection(USERS))
        if (method, path) == ("GET", "/projects"):
            return httpx.Response(200, json=_collection(PROJECTS))
        if (method, path) == ("GET", "/meetings"):
            return httpx.Response(200, json=_collection(self.meetings))
        if (method, path) == ("POST", "/meetings"):
            meeting = _meeting(30, body["startTime"], body["startTime"])
            return httpx.Response(201, json={**meeting, **body, "_links": meeting["_links"]})
        if (method, path) == ("GET", "/meetings/30"):
            return httpx.Response(200, json=_meeting(30, "x", "x", lockVersion=2))
        if (method, path) == ("PATCH", "/meetings/30"):
            return httpx.Response(200, json=_meeting(30, "x", "x"))
        if (method, path) == ("POST", "/meeting_agenda_items"):
            return httpx.Response(201, json={"id": 55})
        if (method, path) == ("POST", "/meeting_outcomes"):
            return httpx.Response(201, json={"id": 1})
        if (method, path) == ("GET", "/work_packages"):
            wp = {
                "id": 40,
                "subject": "Entrega de diseños",
                "dueDate": "2026-09-22",
                "_links": {
                    "type": {"title": "Hito"},
                    "project": _link("projects", 6, "Web corporativa"),
                },
            }
            return httpx.Response(200, json=_collection([wp]))
        return httpx.Response(500)

    def calls(self, method: str, path: str) -> list[dict]:
        return [b for m, p, b in self.requests if (m, p) == (method, path)]


@pytest.fixture
def fake() -> FakeOpenProject:
    return FakeOpenProject()


@pytest.fixture
def op(fake: FakeOpenProject) -> OpenProjectClient:
    return OpenProjectClient(CONFIG, transport=httpx.MockTransport(fake))


def test_view_lists_meetings_in_range_and_due_work(op, fake):
    events = asyncio.run(
        op_calendar.get_calendar_view(
            CONFIG, "2026-09-21T00:00:00", "2026-09-28T00:00:00", timezone=TZ, client=op
        )
    )
    assert [e["id"] for e in events] == ["1", "wp-40"]
    meeting = events[0]
    assert meeting["subject"] == "Reunión 1 (Web corporativa)"
    assert meeting["start"]["dateTime"] == "2026-09-21T10:00:00+02:00"
    assert meeting["webLink"] == "https://jarvis.ts.net:8445/meetings/1"
    assert events[1]["isAllDay"] and events[1]["start"]["dateTime"] == "2026-09-22"
    filters = [p for m, p, _ in fake.requests if p == "/work_packages"]
    assert filters


def test_create_event_invites_users_and_returns_externals(op, fake):
    result = asyncio.run(
        op_calendar.create_event(
            CONFIG,
            "Seguimiento",
            "2026-09-24T10:00:00",
            "2026-09-24T11:30:00",
            ["ana@example.com", "cliente@panaderia.es"],
            "Revisar maquetas",
            timezone=TZ,
            project="web corporativa",
            client=op,
        )
    )
    created = fake.calls("POST", "/meetings")[0]
    assert created["startTime"] == "2026-09-24T08:00:00Z"
    assert created["duration"] == "PT1H30M"
    assert created["_links"]["project"]["href"] == "/api/v3/projects/6"
    assert fake.calls("POST", "/meeting_agenda_items")[0]["notes"]["raw"] == "Revisar maquetas"
    publish = fake.calls("PATCH", "/meetings/30")[0]
    assert publish["state"] == "open" and publish["notify"] is True
    assert publish["lockVersion"] == 2
    # Ana (usuaria) y el propietario; Jarvis no, que su correo no existe.
    hrefs = [p["href"] for p in publish["_links"]["participants"]]
    assert hrefs == ["/api/v3/users/9", "/api/v3/users/4"]
    assert result["external_attendees"] == ["cliente@panaderia.es"]
    assert result["project"] == "Web corporativa"


def test_create_event_without_project_goes_to_agenda(op, fake):
    asyncio.run(
        op_calendar.create_event(
            CONFIG, "Dentista", "2026-09-24T10:00:00", "2026-09-24T11:00:00", timezone=TZ,
            client=op,
        )
    )  # fmt: skip
    assert fake.calls("POST", "/meetings")[0]["_links"]["project"]["href"] == "/api/v3/projects/7"


def test_record_minutes_adds_outcomes_while_in_progress_and_closes(op, fake):
    start = datetime.datetime(2026, 9, 18, 9, 0, tzinfo=datetime.UTC)
    op.record_minutes(
        {"id": 6},
        "Kick-off",
        start,
        75,
        summary="Resumen",
        decisions=["WordPress"],
        work_packages=[{"id": 38}],
    )
    assert fake.calls("POST", "/meetings")[0]["duration"] == "PT1H15M"
    states = [b["state"] for b in fake.calls("PATCH", "/meetings/30")]
    assert states == ["in_progress", "closed"]
    outcomes = fake.calls("POST", "/meeting_outcomes")
    assert [o["kind"] for o in outcomes] == ["decision", "work_package"]
    assert outcomes[1]["_links"]["workPackage"]["href"] == "/api/v3/work_packages/38"
    # Las reuniones pasadas no mandan invitaciones.
    assert all(b["notify"] is False for b in fake.calls("PATCH", "/meetings/30"))


def test_invitation_ics_is_a_request():
    ics = op_calendar.invitation_ics(
        "Seguimiento",
        "2026-09-24T10:00:00",
        "2026-09-24T11:00:00",
        ["cliente@panaderia.es"],
        organizer="jarvis@example.com",
        timezone=TZ,
        url="https://jarvis.ts.net:8445/meetings/30",
    ).decode()
    assert "METHOD:REQUEST" in ics
    assert "mailto:cliente@panaderia.es" in ics
    assert "TZID=Europe/Madrid" in ics


def test_openproject_backend_needs_pm_profile(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    monkeypatch.setattr("packages.openproject.config.RUNTIME_DIR", tmp_path)
    settings = Settings(calendar_provider="openproject")
    with pytest.raises(ProviderUnavailableError):
        calendar_backend_from_settings(settings, lambda: None)


def test_openproject_backend_reads_key_from_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENPROJECT_API_KEY", raising=False)
    (tmp_path / "openproject_api_key").write_text("abc\n")
    monkeypatch.setattr("packages.openproject.config.RUNTIME_DIR", tmp_path)
    backend = calendar_backend_from_settings(
        Settings(calendar_provider="openproject"), lambda: None
    )
    assert backend.config.api_key == "abc"
