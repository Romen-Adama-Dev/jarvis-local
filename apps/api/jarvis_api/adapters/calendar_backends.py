"""Backends de calendario intercambiables para `/v1/calendar` (ver docs/CALENDAR.md).

`CALENDAR_PROVIDER=caldav` (por defecto) usa `packages/caldavcal` (Nextcloud, iCloud,
Fastmail, Radicale...); `CALENDAR_PROVIDER=msgraph` usa `packages/msgraph` (requiere
registro de app en Azure, docs/MSGRAPH.md). Los dos devuelven eventos con la forma de
Graph.
"""

from collections.abc import Callable
from typing import Any, Protocol

from packages.caldavcal import calendar as caldav_calendar
from packages.caldavcal.calendar import CalDavConfig
from packages.core.errors import ProviderUnavailableError
from packages.core.settings import Settings
from packages.msgraph import calendar as graph_calendar
from packages.msgraph.client import MsGraphClient


class CalendarBackend(Protocol):
    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]: ...

    async def create_event(
        self, subject: str, start: str, end: str, attendees: list[str], body: str
    ) -> dict[str, Any]: ...


class GraphCalendarBackend:
    def __init__(self, client: MsGraphClient, timezone: str) -> None:
        self._client = client
        self._timezone = timezone

    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]:
        return await graph_calendar.get_calendar_view(self._client, start, end)

    async def create_event(
        self, subject: str, start: str, end: str, attendees: list[str], body: str
    ) -> dict[str, Any]:
        return await graph_calendar.create_event(
            self._client,
            subject=subject,
            start=start,
            end=end,
            attendees=attendees,
            body=body,
            timezone=self._timezone,
        )


class CalDavCalendarBackend:
    def __init__(self, config: CalDavConfig) -> None:
        self.config = config

    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]:
        return await caldav_calendar.get_calendar_view(self.config, start, end)

    async def create_event(
        self, subject: str, start: str, end: str, attendees: list[str], body: str
    ) -> dict[str, Any]:
        return await caldav_calendar.create_event(
            self.config, subject=subject, start=start, end=end, attendees=attendees, body=body
        )


def calendar_backend_from_settings(
    settings: Settings, graph_client: Callable[[], MsGraphClient]
) -> CalendarBackend:
    provider = settings.calendar_provider.strip().lower()
    if provider == "caldav":
        if not settings.caldav_url:
            raise ProviderUnavailableError(
                "Calendario sin configurar (falta CALDAV_URL). Ejecuta scripts/configure-mail "
                "(ver docs/CALENDAR.md)."
            )
        return CalDavCalendarBackend(
            CalDavConfig(
                url=settings.caldav_url,
                username=settings.caldav_username or settings.mail_username,
                password=settings.caldav_password or settings.mail_password,
                calendar_name=settings.caldav_calendar_name,
                timezone=settings.calendar_timezone,
            )
        )
    if provider == "msgraph":
        return GraphCalendarBackend(graph_client(), settings.calendar_timezone)
    raise ProviderUnavailableError(
        f"CALENDAR_PROVIDER desconocido: '{settings.calendar_provider}' (valores: caldav, msgraph)"
    )
