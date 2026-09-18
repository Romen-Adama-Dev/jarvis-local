import os
import re
import time

import httpx
from mcp.server.fastmcp import FastMCP

JARVIS_API_URL = os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
JARVIS_API_INTERNAL_TOKEN = os.environ["JARVIS_API_INTERNAL_TOKEN"]
JARVIS_OWNER_TELEGRAM_ID = int(os.environ["JARVIS_OWNER_TELEGRAM_ID"])

mcp = FastMCP("jarvis-calendar")

_client = httpx.Client(
    base_url=JARVIS_API_URL,
    headers={"Authorization": f"Bearer {JARVIS_API_INTERNAL_TOKEN}"},
    timeout=60.0,
)


def _split_attendees(attendees: str) -> list[str]:
    return [a for a in re.split(r"[,\s]+", attendees.strip()) if a]


def _api_error(response: httpx.Response, action: str) -> str | None:
    """Mensaje legible de la API (p. ej. "Calendario sin configurar...") en vez de una
    excepción."""
    if response.status_code < 400:
        return None
    try:
        message = response.json().get("message")
    except ValueError:
        message = None
    return message or f"No se pudo {action} ({response.status_code})."


@mcp.tool()
def jarvis_calendar_availability(start: str, end: str) -> str:
    """Consulta los eventos del calendario del propietario entre `start` y `end`.
    Las fechas van en ISO 8601, p. ej. 2026-09-15T09:00:00."""
    response = _client.get("/v1/calendar/events", params={"start": start, "end": end})
    if error := _api_error(response, "consultar el calendario"):
        return error
    events = response.json()
    if not events:
        return "Sin eventos en ese rango."
    lines = []
    for event in events:
        subject = event.get("subject") or "(sin asunto)"
        event_start = event.get("start", {}).get("dateTime", "?")
        event_end = event.get("end", {}).get("dateTime", "?")
        organizer = (
            event.get("organizer", {}).get("emailAddress", {}).get("address") or "desconocido"
        )
        if event.get("isAllDay"):
            line = f"- {event_start}: {subject}"
        else:
            line = f"- {subject}: {event_start}–{event_end} (organizador: {organizer})"
        if location := (event.get("location") or {}).get("displayName"):
            line += f", en {location}"
        if event.get("webLink"):
            line += f" {event['webLink']}"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def jarvis_calendar_propose_event(
    subject: str,
    start: str,
    end: str,
    attendees: str = "",
    body: str = "",
    project: str = "",
    location: str = "",
) -> str:
    """Propone (NO crea todavía) un evento de calendario (una reunión en OpenProject).
    `start`/`end` en ISO 8601, p. ej. 2026-09-15T09:00:00. `attendees` es una lista de
    emails separados por comas o espacios (opcional). `project`: proyecto de OpenProject
    al que pertenece la reunión, si el usuario lo nombra (vacío = "Agenda"). `location`:
    sala o enlace de videollamada.

    Si hay `attendees`, esto invitará a terceros al confirmarse — nunca llames a
    jarvis_calendar_confirm_event sin que el usuario lo haya pedido explícitamente.
    """
    response = _client.post(
        "/v1/calendar/draft",
        json={
            "subject": subject,
            "start": start,
            "end": end,
            "attendees": _split_attendees(attendees),
            "body": body,
            "project": project,
            "location": location,
            "telegram_user_id": JARVIS_OWNER_TELEGRAM_ID,
        },
    )
    if error := _api_error(response, "preparar la propuesta"):
        return error
    draft = response.json()
    minutes = max(1, int(draft["expires_at"] - time.time()) // 60)
    return (
        f"Propuesta lista — {draft['summary']}.\n"
        "Enséñasela a Romen y pregúntale si la creas. Si dice que sí, llama TÚ a "
        f"jarvis_calendar_confirm_event con token=\"{draft['token']}\" (no le pidas que "
        f"escriba ningún comando). Caduca en {minutes} min."
    )


@mcp.tool()
def jarvis_calendar_confirm_event(token: str) -> str:
    """Confirma y crea de verdad un evento de calendario previamente propuesto con
    jarvis_calendar_propose_event. Si la propuesta incluía invitados, esto les envía
    invitaciones reales: solo llama a esta herramienta cuando el usuario lo haya
    pedido explícitamente."""
    response = _client.post(
        f"/v1/calendar/draft/{token}/confirm",
        json={"telegram_user_id": JARVIS_OWNER_TELEGRAM_ID},
    )
    if error := _api_error(response, "confirmar el evento"):
        return error
    result = response.json()
    lines = [f"Evento creado: {result.get('webLink') or result.get('id')}"]
    if result.get("project"):
        lines.append(f"Reunión en el proyecto «{result['project']}» de OpenProject.")
    invited = result.get("invited_by_email")
    if isinstance(invited, list):
        lines.append(f"Invitación con .ics enviada por correo a {', '.join(invited)}.")
    elif invited:
        lines.append(f"Invitación por correo a los externos {invited}.")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
