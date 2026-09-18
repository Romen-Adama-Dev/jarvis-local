from typing import Any

from fastapi import APIRouter

from apps.api.jarvis_api.deps import (
    CalendarBackendDep,
    ConfirmationServiceDep,
    SettingsDep,
    get_mail_backend,
)
from apps.api.jarvis_api.schemas import (
    CalendarConfirmRequest,
    CalendarDraftRequest,
    CalendarDraftResponse,
)
from packages.core.attachments import Attachment
from packages.core.errors import JarvisError, ValidationFailedError
from packages.core.logging import get_logger
from packages.openproject.calendar import invitation_ics

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


@router.get("/events")
async def get_events(start: str, end: str, backend: CalendarBackendDep) -> list[dict[str, Any]]:
    return await backend.get_calendar_view(start, end)


@router.post("/draft", response_model=CalendarDraftResponse, status_code=202)
async def draft_event(
    payload: CalendarDraftRequest,
    confirmation_service: ConfirmationServiceDep,
    # Sin usar aquí: resolverlo hace que la propuesta falle ya si no hay calendario.
    _backend: CalendarBackendDep,
) -> CalendarDraftResponse:
    if not payload.subject or not payload.start or not payload.end:
        raise ValidationFailedError("subject, start y end son obligatorios")

    summary = f"Evento '{payload.subject}' de {payload.start} a {payload.end}"
    if payload.project:
        summary += f" en el proyecto {payload.project}"
    if payload.location:
        summary += f" ({payload.location})"
    if payload.attendees:
        summary += f", invita a {', '.join(payload.attendees)}"

    pending = await confirmation_service.request(
        payload.telegram_user_id,
        action="create_event",
        summary=summary,
        payload=payload.model_dump(),
    )
    return CalendarDraftResponse(
        token=pending.token, summary=pending.summary, expires_at=pending.expires_at
    )


@router.post("/draft/{token}/confirm")
async def confirm_event(
    token: str,
    payload: CalendarConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
    backend: CalendarBackendDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    draft = pending.payload
    event = await backend.create_event(
        subject=draft["subject"],
        start=draft["start"],
        end=draft["end"],
        attendees=draft.get("attendees") or [],
        body=draft.get("body") or "",
        project=draft.get("project") or "",
        location=draft.get("location") or "",
    )
    result: dict[str, Any] = {"created": True, "id": event["id"], "webLink": event.get("webLink")}
    if event.get("project"):
        result["project"] = event["project"]
    external = event.get("external_attendees") or []
    if external:
        result["invited_by_email"] = await _email_invitation(settings, draft, event, external)
    return result


async def _email_invitation(
    settings: Any, draft: dict[str, Any], event: dict[str, Any], to: list[str]
) -> list[str] | str:
    """Invitación .ics por el correo de Jarvis a quien no es usuario de OpenProject. Ya
    está confirmada (la propuesta nombraba a los invitados); si no hay correo configurado,
    se devuelve el motivo para que el agente lo diga."""
    try:
        mail = get_mail_backend(settings)
        ics = invitation_ics(
            draft["subject"],
            draft["start"],
            draft["end"],
            to,
            organizer=settings.mail_from or settings.mail_username,
            timezone=settings.calendar_timezone,
            body=draft.get("body") or "",
            url=event.get("webLink") or "",
        )
        text = f"Te invito a «{draft['subject']}» ({draft['start']} – {draft['end']})."
        if draft.get("location"):
            text += f"\nLugar: {draft['location']}"
        if draft.get("body"):
            text += f"\n\n{draft['body']}"
        await mail.send_mail(
            to=to,
            subject=f"Invitación: {draft['subject']}",
            body=text,
            attachments=[Attachment("invitacion.ics", ics, "text/calendar")],
        )
    except JarvisError as exc:
        logger.warning("calendar_invitation_not_sent", error=exc.message)
        return f"no enviada: {exc.message}"
    return to
