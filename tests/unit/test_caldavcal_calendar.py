import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar, Event

from packages.caldavcal.calendar import CalDavConfig, create_event, get_calendar_view
from packages.core.errors import ValidationFailedError

CONFIG = CalDavConfig(
    url="https://dav.example.com/", username="jarvis@example.com", password="app-password"
)
MADRID = ZoneInfo("Europe/Madrid")


def _event(**props) -> SimpleNamespace:
    event = Event()
    for name, value in props.items():
        if isinstance(value, list):
            for item in value:
                event.add(name, item)
        else:
            event.add(name, value)
    return SimpleNamespace(icalendar_component=event)


class FakeCalendar:
    def __init__(self, results=None) -> None:
        self.results = results or []
        self.search_kwargs: dict | None = None
        self.saved: list[str] = []

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        return self.results

    def save_event(self, ical: str):
        self.saved.append(ical)


async def test_get_calendar_view_maps_events_to_graph_shape_sorted_by_start():
    calendar = FakeCalendar(
        [
            _event(
                uid="b",
                summary="Comité",
                dtstart=datetime.datetime(2026, 9, 16, 8, 0, tzinfo=datetime.UTC),
                dtend=datetime.datetime(2026, 9, 16, 9, 0, tzinfo=datetime.UTC),
                organizer="mailto:ana@example.com",
                attendee=["mailto:romen@example.com", "MAILTO:luis@example.com"],
            ),
            _event(
                uid="a",
                summary="Festivo",
                dtstart=datetime.date(2026, 9, 15),
                dtend=datetime.date(2026, 9, 16),
            ),
        ]
    )

    events = await get_calendar_view(
        CONFIG, "2026-09-15T00:00:00", "2026-09-17T00:00:00", calendar_factory=lambda _: calendar
    )

    assert calendar.search_kwargs == {
        "start": datetime.datetime(2026, 9, 15, tzinfo=MADRID),
        "end": datetime.datetime(2026, 9, 17, tzinfo=MADRID),
        "event": True,
        "expand": True,
    }
    assert [e["id"] for e in events] == ["a", "b"]
    assert events[0]["start"] == {"dateTime": "2026-09-15", "timeZone": "Europe/Madrid"}
    assert events[1] == {
        "id": "b",
        "subject": "Comité",
        "start": {"dateTime": "2026-09-16T10:00:00+02:00", "timeZone": "Europe/Madrid"},
        "end": {"dateTime": "2026-09-16T11:00:00+02:00", "timeZone": "Europe/Madrid"},
        "organizer": {"emailAddress": {"address": "ana@example.com"}},
        "attendees": [
            {"emailAddress": {"address": "romen@example.com"}, "type": "required"},
            {"emailAddress": {"address": "luis@example.com"}, "type": "required"},
        ],
    }


async def test_create_event_saves_valid_ical_with_attendees_in_local_timezone():
    calendar = FakeCalendar()

    result = await create_event(
        CONFIG,
        subject="Kick-off",
        start="2026-09-20T09:00:00",
        end="2026-09-20T10:00:00",
        attendees=["romen@example.com"],
        body="Orden del día",
        calendar_factory=lambda _: calendar,
    )

    [ical] = calendar.saved
    [vevent] = Calendar.from_ical(ical).walk("VEVENT")
    assert str(vevent["uid"]) == result["id"]
    assert result["id"].endswith("@jarvis-local")
    assert str(vevent["summary"]) == "Kick-off"
    assert str(vevent["description"]) == "Orden del día"
    assert vevent["dtstart"].dt == datetime.datetime(2026, 9, 20, 9, 0, tzinfo=MADRID)
    assert str(vevent["organizer"]) == "mailto:jarvis@example.com"
    assert str(vevent["attendee"]) == "mailto:romen@example.com"
    assert vevent["attendee"].params["RSVP"] == "TRUE"


async def test_create_event_rejects_end_before_start():
    with pytest.raises(ValidationFailedError):
        await create_event(
            CONFIG,
            "x",
            "2026-09-20T10:00:00",
            "2026-09-20T09:00:00",
            calendar_factory=lambda _: FakeCalendar(),
        )


async def test_create_event_rejects_invalid_attendee():
    with pytest.raises(ValidationFailedError):
        await create_event(
            CONFIG,
            "x",
            "2026-09-20T09:00:00",
            "2026-09-20T10:00:00",
            attendees=["romen@example.com\nATTENDEE:mailto:otro@example.com"],
            calendar_factory=lambda _: FakeCalendar(),
        )


async def test_get_calendar_view_rejects_invalid_date():
    with pytest.raises(ValidationFailedError):
        await get_calendar_view(CONFIG, "mañana", "pasado", calendar_factory=lambda _: None)
