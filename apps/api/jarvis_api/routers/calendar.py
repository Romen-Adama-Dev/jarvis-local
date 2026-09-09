from typing import Any

from fastapi import APIRouter

from apps.api.jarvis_api.deps import ConfirmationServiceDep, MsGraphClientDep
from apps.api.jarvis_api.schemas import (
    CalendarConfirmRequest,
    CalendarDraftRequest,
    CalendarDraftResponse,
)
from packages.core.errors import ValidationFailedError
from packages.msgraph.calendar import create_event, get_calendar_view

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


@router.get("/events")
async def get_events(start: str, end: str, client: MsGraphClientDep) -> list[dict[str, Any]]:
    return await get_calendar_view(client, start, end)


@router.post("/draft", response_model=CalendarDraftResponse, status_code=202)
async def draft_event(
    payload: CalendarDraftRequest, confirmation_service: ConfirmationServiceDep
) -> CalendarDraftResponse:
    if not payload.subject or not payload.start or not payload.end:
        raise ValidationFailedError("subject, start y end son obligatorios")

    summary = f"Evento '{payload.subject}' de {payload.start} a {payload.end}"
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
    client: MsGraphClientDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    draft = pending.payload
    event = await create_event(
        client,
        subject=draft["subject"],
        start=draft["start"],
        end=draft["end"],
        attendees=draft.get("attendees") or [],
        body=draft.get("body") or "",
    )
    return {"created": True, "id": event["id"], "webLink": event.get("webLink")}
