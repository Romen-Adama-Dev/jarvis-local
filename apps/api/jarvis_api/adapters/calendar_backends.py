"""Backends de calendario intercambiables para `/v1/calendar` (ver docs/CALENDAR.md).

`CALENDAR_PROVIDER=caldav` (por defecto) usa `packages/caldavcal` (Nextcloud, iCloud,
Fastmail, Radicale...); `CALENDAR_PROVIDER=openproject` usa las reuniones de OpenProject
(perfil pm, `packages/openproject/calendar.py`); `CALENDAR_PROVIDER=msgraph` usa
`packages/msgraph` (requiere registro de app en Azure, docs/MSGRAPH.md). Todos devuelven
eventos con la forma de Graph.

`project` y `location` solo los usa OpenProject (la reunión va a ese proyecto); los demás
los ignoran.
"""

from collections.abc import Callable
from typing import Any, Protocol

from packages.caldavcal import calendar as caldav_calendar
from packages.caldavcal.calendar import CalDavConfig
from packages.core.errors import ProviderUnavailableError
from packages.core.settings import Settings
from packages.msgraph import calendar as graph_calendar
from packages.msgraph.client import MsGraphClient
from packages.openproject import calendar as openproject_calendar
from packages.openproject.client import OpenProjectConfig
from packages.openproject.config import config_from_env as openproject_config


class CalendarBackend(Protocol):
    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]: ...

    async def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str],
        body: str,
        project: str = "",
        location: str = "",
    ) -> dict[str, Any]: ...


class GraphCalendarBackend:
    def __init__(self, client: MsGraphClient, timezone: str) -> None:
        self._client = client
        self._timezone = timezone

    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]:
        return await graph_calendar.get_calendar_view(self._client, start, end)

    async def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str],
        body: str,
        project: str = "",
        location: str = "",
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
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str],
        body: str,
        project: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        return await caldav_calendar.create_event(
            self.config, subject=subject, start=start, end=end, attendees=attendees, body=body
        )


class OpenProjectCalendarBackend:
    def __init__(self, config: OpenProjectConfig, timezone: str, default_project: str) -> None:
        self.config = config
        self._timezone = timezone
        self._default_project = default_project

    async def get_calendar_view(self, start: str, end: str) -> list[dict[str, Any]]:
        return await openproject_calendar.get_calendar_view(
            self.config, start, end, timezone=self._timezone
        )

    async def create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str],
        body: str,
        project: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        return await openproject_calendar.create_event(
            self.config,
            subject=subject,
            start=start,
            end=end,
            attendees=attendees,
            body=body,
            timezone=self._timezone,
            project=project,
            default_project=self._default_project,
            location=location,
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
    if provider == "openproject":
        config = openproject_config()
        if config is None:
            raise ProviderUnavailableError(
                "Calendario de OpenProject sin configurar: activa el perfil `pm` "
                "(docs/OPENPROJECT.md)."
            )
        return OpenProjectCalendarBackend(
            config, settings.calendar_timezone, settings.openproject_calendar_project
        )
    if provider == "msgraph":
        return GraphCalendarBackend(graph_client(), settings.calendar_timezone)
    raise ProviderUnavailableError(
        f"CALENDAR_PROVIDER desconocido: '{settings.calendar_provider}' "
        "(valores: caldav, openproject, msgraph)"
    )
