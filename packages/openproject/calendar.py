"""Calendario sobre OpenProject (`CALENDAR_PROVIDER=openproject`, docs/CALENDAR.md).

La agenda de Jarvis son las **reuniones** de OpenProject: las que se crean desde Telegram,
desde la web o al importar un acta. Consultar disponibilidad devuelve esas reuniones y,
como avisos de día completo, el trabajo abierto que vence en el rango (tareas e hitos).
Mismo contrato que `packages/caldavcal`: funciones async y eventos con la forma de Graph.

Invitados: los que son usuarios de OpenProject entran como participantes y OpenProject
les manda la invitación con su .ics (con SMTP configurado, docs/OPENPROJECT.md); el resto
se devuelve en `external_attendees` para que la API les mande la invitación por el
correo de Jarvis (`invitation_ics`). El propietario participa siempre, así la reunión le
llega a su calendario (correo con .ics y suscripción iCal de "Mis reuniones").
"""

import asyncio
import datetime
import re
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from packages.core.errors import NotFoundError, ValidationFailedError
from packages.openproject.client import OpenProjectClient, OpenProjectConfig

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+")


def _parse(value: str, tz: ZoneInfo) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailedError(f"Fecha ISO 8601 inválida: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


def _meeting_to_graph(op: OpenProjectClient, meeting: dict, tz: ZoneInfo) -> dict[str, Any]:
    start = datetime.datetime.fromisoformat(meeting["startTime"].replace("Z", "+00:00"))
    end = datetime.datetime.fromisoformat(meeting["endTime"].replace("Z", "+00:00"))
    links = meeting["_links"]
    return {
        "id": str(meeting["id"]),
        "subject": f"{meeting['title']} ({links['project']['title']})",
        "start": {"dateTime": start.astimezone(tz).isoformat(), "timeZone": tz.key},
        "end": {"dateTime": end.astimezone(tz).isoformat(), "timeZone": tz.key},
        "location": {"displayName": meeting.get("location") or ""},
        "organizer": {"emailAddress": {"address": links.get("author", {}).get("title", "")}},
        "attendees": [
            {"emailAddress": {"address": p.get("title", "")}, "type": "required"}
            for p in links.get("participants", [])
        ],
        "webLink": op.meeting_url(meeting),
    }


def _work_package_to_graph(op: OpenProjectClient, wp: dict, tz: ZoneInfo) -> dict[str, Any]:
    links = wp["_links"]
    day = wp.get("dueDate") or wp.get("date")
    return {
        "id": f"wp-{wp['id']}",
        "subject": (
            f"Vence #{wp['id']} [{links['type']['title']}] {wp['subject']} "
            f"({links['project']['title']})"
        ),
        "start": {"dateTime": day, "timeZone": tz.key},
        "end": {"dateTime": day, "timeZone": tz.key},
        "isAllDay": True,
        "organizer": {"emailAddress": {"address": ""}},
        "attendees": [],
        "webLink": op.work_package_url(wp),
    }


def _view_sync(
    op: OpenProjectClient, start: datetime.datetime, end: datetime.datetime, tz: ZoneInfo
) -> list[dict[str, Any]]:
    events = [_meeting_to_graph(op, m, tz) for m in op.meetings(start, end)]
    last_day = (end - datetime.timedelta(microseconds=1)).astimezone(tz).date()
    for wp in op.dated_work_packages(start.astimezone(tz).date(), last_day):
        events.append(_work_package_to_graph(op, wp, tz))
    return sorted(events, key=lambda e: e["start"]["dateTime"])


async def get_calendar_view(
    config: OpenProjectConfig, start: str, end: str, *, timezone: str, client=None
) -> list[dict[str, Any]]:
    tz = ZoneInfo(timezone)
    op = client or OpenProjectClient(config)
    return await asyncio.to_thread(_view_sync, op, _parse(start, tz), _parse(end, tz), tz)


def _agenda_project(op: OpenProjectClient, name: str) -> dict:
    """Proyecto donde van las reuniones que no son de ningún proyecto; se crea si falta."""
    try:
        return op.find_project(name)
    except (NotFoundError, ValidationFailedError):
        return op.create_project(name, description="Reuniones y citas creadas por Jarvis.")


def _create_sync(
    op: OpenProjectClient,
    subject: str,
    start: datetime.datetime,
    end: datetime.datetime,
    attendees: list[str],
    body: str,
    project: str,
    default_project: str,
    location: str,
) -> dict[str, Any]:
    if end <= start:
        raise ValidationFailedError("El evento debe terminar después de empezar")
    for address in attendees:
        if not _EMAIL_RE.fullmatch(address):
            raise ValidationFailedError(f"Dirección de invitado inválida: {address}")
    proj = op.find_project(project) if project else _agenda_project(op, default_project)
    users = op.users_by_email()
    participants, external = [], []
    for address in attendees:
        user = users.get(address.lower())
        (participants if user else external).append(user or address)
    owner = op.owner()
    if owner and all(p["id"] != owner["id"] for p in participants):
        participants.append(owner)
    meeting = op.create_meeting(
        proj, subject, start, end, participants=participants, location=location, notes=body
    )
    return {
        "id": str(meeting["id"]),
        "webLink": op.meeting_url(meeting),
        "project": proj["name"],
        "external_attendees": external,
    }


async def create_event(
    config: OpenProjectConfig,
    subject: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    body: str | None = None,
    *,
    timezone: str,
    project: str = "",
    default_project: str = "Agenda",
    location: str = "",
    client=None,
) -> dict[str, Any]:
    """Crea una reunión en OpenProject. Invita de verdad: llamar solo tras confirmación."""
    tz = ZoneInfo(timezone)
    op = client or OpenProjectClient(config)
    return await asyncio.to_thread(
        _create_sync,
        op,
        subject,
        _parse(start, tz),
        _parse(end, tz),
        attendees or [],
        body or "",
        project,
        default_project,
        location,
    )


def invitation_ics(
    subject: str,
    start: str,
    end: str,
    attendees: list[str],
    *,
    organizer: str,
    timezone: str,
    body: str = "",
    url: str = "",
) -> bytes:
    """Invitación iCalendar (METHOD:REQUEST) para quien no es usuario de OpenProject:
    Gmail, Outlook o el calendario del iPhone la muestran con aceptar/rechazar."""
    tz = ZoneInfo(timezone)
    event = Event()
    event.add("uid", f"{uuid.uuid4()}@jarvis-local")
    event.add("dtstamp", datetime.datetime.now(datetime.UTC))
    event.add("dtstart", _parse(start, tz))
    event.add("dtend", _parse(end, tz))
    event.add("summary", subject)
    if body or url:
        event.add("description", "\n\n".join(x for x in (body, url) if x))
    if url:
        event.add("url", url)
    if organizer:
        event.add("organizer", f"mailto:{organizer}")
    for address in attendees:
        event.add(
            "attendee",
            f"mailto:{address}",
            parameters={"ROLE": "REQ-PARTICIPANT", "RSVP": "TRUE"},
        )
    calendar = Calendar()
    calendar.add("prodid", "-//jarvis-local//OpenProject//ES")
    calendar.add("version", "2.0")
    calendar.add("method", "REQUEST")
    calendar.add_component(event)
    calendar.add_missing_timezones()
    return calendar.to_ical()
