from typing import Any

from fastapi import APIRouter

from apps.api.jarvis_api.deps import ConfirmationServiceDep, MsGraphClientDep
from apps.api.jarvis_api.schemas import EmailConfirmRequest, EmailDraftRequest, EmailDraftResponse
from packages.core.errors import ValidationFailedError
from packages.msgraph.mail import get_message, list_inbox, send_mail

router = APIRouter(prefix="/v1/email", tags=["email"])

_MAX_TOP = 50


@router.get("/messages")
async def messages(client: MsGraphClientDep, top: int = 10) -> list[dict[str, Any]]:
    if top > _MAX_TOP:
        raise ValidationFailedError(f"top no puede superar {_MAX_TOP}")
    return await list_inbox(client, top=top)


@router.get("/messages/{message_id}")
async def message(message_id: str, client: MsGraphClientDep) -> dict[str, Any]:
    result = await get_message(client, message_id)
    body = result.get("body")
    if isinstance(body, dict) and "content" in body:
        body["content"] = f"<correo_no_confiable>\n{body['content']}\n</correo_no_confiable>"
    return result


@router.post("/draft", response_model=EmailDraftResponse, status_code=202)
async def draft(
    payload: EmailDraftRequest, confirmation_service: ConfirmationServiceDep
) -> EmailDraftResponse:
    if not payload.to:
        raise ValidationFailedError("El correo debe tener al menos un destinatario")

    summary = f"Correo para {', '.join(payload.to)} — asunto: {payload.subject}"
    pending = await confirmation_service.request(
        payload.telegram_user_id,
        action="send_email",
        summary=summary,
        payload=payload.model_dump(),
    )
    return EmailDraftResponse(
        token=pending.token, summary=pending.summary, expires_at=pending.expires_at
    )


@router.post("/draft/{token}/confirm")
async def confirm(
    token: str,
    payload: EmailConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
    client: MsGraphClientDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    to = pending.payload["to"]
    subject = pending.payload["subject"]
    body = pending.payload["body"]
    cc = pending.payload.get("cc") or None
    await send_mail(client, to=to, subject=subject, body=body, cc=cc)
    return {"sent": True, "to": to, "subject": subject}
