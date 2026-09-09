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
    timeout=30.0,
)


def _split_attendees(attendees: str) -> list[str]:
    return [a for a in re.split(r"[,\s]+", attendees.strip()) if a]


@mcp.tool()
def jarvis_calendar_availability(start: str, end: str) -> str:
    """Consulta los eventos del calendario del propietario entre `start` y `end`.
    Las fechas van en ISO 8601, p. ej. 2026-09-15T09:00:00."""
    response = _client.get("/v1/calendar/events", params={"start": start, "end": end})
    response.raise_for_status()
    events = response.json()
    if not events:
        return "Sin eventos en ese rango."
    lines = []
    for event in events:
        subject = event.get("subject") or "(sin asunto)"
        event_start = event.get("start", {}).get("dateTime", "?")
        event_end = event.get("end", {}).get("dateTime", "?")
        organizer = (
            event.get("organizer", {}).get("emailAddress", {}).get("address", "desconocido")
        )
        lines.append(f"- {subject}: {event_start}–{event_end} (organizador: {organizer})")
    return "\n".join(lines)


@mcp.tool()
def jarvis_calendar_propose_event(
    subject: str, start: str, end: str, attendees: str = "", body: str = ""
) -> str:
    """Propone (NO crea todavía) un evento de calendario. `start`/`end` en ISO 8601,
    p. ej. 2026-09-15T09:00:00. `attendees` es una lista de emails separados por
    comas o espacios (opcional).

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
            "telegram_user_id": JARVIS_OWNER_TELEGRAM_ID,
        },
    )
    response.raise_for_status()
    draft = response.json()
    ttl = int(draft["expires_at"] - time.time())
    return (
        f"Propuesta lista — {draft['summary']}. Para crearla, confirma explícitamente y "
        f"usa jarvis_calendar_confirm_event('{draft['token']}'). Caduca en {ttl}s."
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
    if response.status_code >= 400:
        detail = response.json()
        return detail.get("message") or f"No se pudo confirmar el evento ({response.status_code})"
    result = response.json()
    return f"Evento creado: {result.get('webLink') or result.get('id')}"


if __name__ == "__main__":
    mcp.run()
