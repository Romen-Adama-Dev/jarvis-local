"""Operaciones de calendario sobre Microsoft Graph.

Funciones planas que reciben un `MsGraphClient` ya autenticado (ver
`packages/msgraph/client.py`) como primer argumento. Deliberadamente sin
estado propio: no cachean nada ni conocen la autenticación, solo construyen
las peticiones REST de `/me/calendarview` y `/me/events` con la forma que
espera Graph. El flujo de proponer/confirmar antes de crear un evento vive
en `apps/api/jarvis_api/routers/calendar.py`, no aquí.
"""

from typing import Any

from packages.msgraph.client import MsGraphClient


async def get_calendar_view(client: MsGraphClient, start: str, end: str) -> list[dict[str, Any]]:
    """Consulta los eventos del calendario del propietario entre `start` y `end`.

    `start`/`end` son cadenas ISO 8601 (p. ej. `2026-09-15T00:00:00`).
    """
    response = await client.get(
        "/me/calendarview",
        params={
            "startDateTime": start,
            "endDateTime": end,
            "$select": "id,subject,start,end,organizer,attendees",
            "$orderby": "start/dateTime",
        },
    )
    return response["value"]


async def create_event(
    client: MsGraphClient,
    subject: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    body: str | None = None,
    timezone: str = "Europe/Madrid",
) -> dict[str, Any]:
    """Crea un evento en el calendario del propietario.

    Si `attendees` no está vacío, Graph enviará invitaciones reales a esas
    direcciones al crear el evento: quien llame a esta función debe haber
    obtenido confirmación explícita antes (ver el router de calendario).
    """
    payload = {
        "subject": subject,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
        "attendees": [
            {"emailAddress": {"address": address}, "type": "required"}
            for address in (attendees or [])
        ],
        "body": {"contentType": "Text", "content": body or ""},
    }
    return await client.post("/me/events", json=payload)
