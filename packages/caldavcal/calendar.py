"""Calendario genérico sobre CalDAV (Nextcloud, iCloud, Fastmail, Radicale, SOGo...).

Alternativa a `packages/msgraph/calendar.py` sin Azure. Mismo contrato: funciones
async planas, sin confirmación (vive en `apps/api/jarvis_api/routers/calendar.py`), y
eventos devueltos con la forma de Graph (`subject`, `start.dateTime`,
`organizer.emailAddress.address`...) para que `/v1/calendar` y el servidor MCP
`jarvis-calendar` no dependan del proveedor.

La biblioteca `caldav` es síncrona: se delega en un hilo.
"""

import asyncio
import datetime
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import caldav
import requests
from caldav.lib import error as caldav_error
from icalendar import Calendar, Event

from packages.core.errors import ProviderUnavailableError, ValidationFailedError
from packages.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_SECONDS = 30
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+")


@dataclass(frozen=True, slots=True)
class CalDavConfig:
    url: str
    username: str
    password: str
    # Nombre visible del calendario; vacío = el primero de la cuenta.
    calendar_name: str = ""
    timezone: str = "Europe/Madrid"


# Devuelve un objeto con la interfaz de caldav.Calendar (inyectable en tests).
CalendarFactory = Callable[[CalDavConfig], Any]


def _open_calendar(config: CalDavConfig) -> Any:
    client = caldav.DAVClient(
        url=config.url,
        username=config.username or None,
        password=config.password or None,
        timeout=_TIMEOUT_SECONDS,
    )
    calendars = client.principal().calendars()
    if not calendars:
        raise ProviderUnavailableError("La cuenta CalDAV no tiene ningún calendario")
    if not config.calendar_name:
        return calendars[0]
    for calendar in calendars:
        if calendar.name == config.calendar_name:
            return calendar
    available = ", ".join(str(c.name) for c in calendars)
    raise ProviderUnavailableError(
        f"No existe el calendario CalDAV '{config.calendar_name}'. Disponibles: {available}"
    )


async def _in_thread(func: Callable[..., Any], *args: Any) -> Any:
    try:
        return await asyncio.to_thread(func, *args)
    except caldav_error.AuthorizationError as exc:
        raise ProviderUnavailableError(
            "El servidor CalDAV rechazó el usuario o la contraseña. Usa una contraseña de "
            "aplicación, no la de la cuenta (ver docs/CALENDAR.md)."
        ) from exc
    except (caldav_error.DAVError, requests.RequestException, OSError) as exc:
        logger.error("caldav_request_failed", error=str(exc))
        raise ProviderUnavailableError(f"Servidor CalDAV no disponible: {exc}") from exc


def _parse_datetime(value: str, tz: ZoneInfo) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailedError(f"Fecha ISO 8601 inválida: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


def _to_iso(value: Any, tz: ZoneInfo) -> str:
    if isinstance(value, datetime.datetime):
        return (value.astimezone(tz) if value.tzinfo else value).isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    return ""


def _mailto(value: Any) -> str:
    return re.sub(r"^mailto:", "", str(value), flags=re.IGNORECASE) if value else ""


def _event_to_graph(component: Any, tz: ZoneInfo) -> dict[str, Any]:
    dtstart = component.get("dtstart")
    dtend = component.get("dtend")
    duration = component.get("duration")
    start = dtstart.dt if dtstart is not None else None
    if dtend is not None:
        end = dtend.dt
    elif duration is not None and start is not None:
        end = start + duration.dt
    else:
        end = start
    attendees = component.get("attendee") or []
    if not isinstance(attendees, list):
        attendees = [attendees]
    return {
        "id": str(component.get("uid", "")),
        "subject": str(component.get("summary", "")),
        "start": {"dateTime": _to_iso(start, tz), "timeZone": tz.key},
        "end": {"dateTime": _to_iso(end, tz), "timeZone": tz.key},
        "organizer": {"emailAddress": {"address": _mailto(component.get("organizer"))}},
        "attendees": [
            {"emailAddress": {"address": _mailto(a)}, "type": "required"} for a in attendees
        ],
    }


def _calendar_view_sync(
    config: CalDavConfig,
    start: datetime.datetime,
    end: datetime.datetime,
    calendar_factory: CalendarFactory,
) -> list[dict[str, Any]]:
    calendar = calendar_factory(config)
    results = calendar.search(start=start, end=end, event=True, expand=True)
    tz = ZoneInfo(config.timezone)
    events = [_event_to_graph(result.icalendar_component, tz) for result in results]
    return sorted(events, key=lambda event: event["start"]["dateTime"])


def build_event_ical(
    config: CalDavConfig,
    subject: str,
    start: datetime.datetime,
    end: datetime.datetime,
    attendees: list[str],
    body: str,
) -> tuple[str, str]:
    """Construye el VCALENDAR de un evento nuevo. Devuelve `(uid, ical)`."""
    if end <= start:
        raise ValidationFailedError("El evento debe terminar después de empezar")
    for address in attendees:
        if not _EMAIL_RE.fullmatch(address):
            raise ValidationFailedError(f"Dirección de invitado inválida: {address}")

    uid = f"{uuid.uuid4()}@jarvis-local"
    event = Event()
    event.add("uid", uid)
    event.add("dtstamp", datetime.datetime.now(datetime.UTC))
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("summary", subject)
    if body:
        event.add("description", body)
    if _EMAIL_RE.fullmatch(config.username):
        event.add("organizer", f"mailto:{config.username}")
    for address in attendees:
        event.add(
            "attendee",
            f"mailto:{address}",
            parameters={"ROLE": "REQ-PARTICIPANT", "RSVP": "TRUE"},
        )

    calendar = Calendar()
    calendar.add("prodid", "-//jarvis-local//CalDAV//ES")
    calendar.add("version", "2.0")
    calendar.add_component(event)
    calendar.add_missing_timezones()
    return uid, calendar.to_ical().decode()


def _save_event_sync(config: CalDavConfig, ical: str, calendar_factory: CalendarFactory) -> None:
    calendar_factory(config).save_event(ical)


async def get_calendar_view(
    config: CalDavConfig,
    start: str,
    end: str,
    *,
    calendar_factory: CalendarFactory = _open_calendar,
) -> list[dict[str, Any]]:
    """Consulta los eventos entre `start` y `end` (ISO 8601; sin zona horaria se
    interpretan en `config.timezone`), con las recurrencias expandidas."""
    tz = ZoneInfo(config.timezone)
    start_dt = _parse_datetime(start, tz)
    end_dt = _parse_datetime(end, tz)
    return await _in_thread(_calendar_view_sync, config, start_dt, end_dt, calendar_factory)


async def create_event(
    config: CalDavConfig,
    subject: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    body: str | None = None,
    *,
    calendar_factory: CalendarFactory = _open_calendar,
) -> dict[str, Any]:
    """Crea un evento en el calendario configurado.

    Los servidores con planificación implícita (Nextcloud, iCloud, Fastmail...) envían
    invitaciones reales a `attendees` al guardarlo: quien llame a esta función debe
    haber obtenido confirmación explícita antes (ver el router de calendario).
    """
    tz = ZoneInfo(config.timezone)
    uid, ical = build_event_ical(
        config,
        subject,
        _parse_datetime(start, tz),
        _parse_datetime(end, tz),
        attendees or [],
        body or "",
    )
    await _in_thread(_save_event_sync, config, ical, calendar_factory)
    return {"id": uid, "webLink": None}
