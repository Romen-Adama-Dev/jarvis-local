import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.jarvis_api.deps import (
    ConfirmationServiceDep,
    DbSession,
    MailBackendDep,
    SettingsDep,
)
from apps.api.jarvis_api.schemas import EmailConfirmRequest, EmailDraftRequest, EmailDraftResponse
from packages.core.attachments import Attachment
from packages.core.db.models import Job
from packages.core.errors import NotFoundError, ValidationFailedError
from packages.core.jobs import FILE_JOB_TYPES
from packages.security.telegram_approval import email_approval_text, send_approval

router = APIRouter(prefix="/v1/email", tags=["email"])

_MAX_TOP = 50


@router.get("/messages")
async def messages(backend: MailBackendDep, top: int = 10) -> list[dict[str, Any]]:
    if top > _MAX_TOP:
        raise ValidationFailedError(f"top no puede superar {_MAX_TOP}")
    return await backend.list_inbox(top)


@router.get("/messages/{message_id}")
async def message(message_id: str, backend: MailBackendDep) -> dict[str, Any]:
    result = await backend.get_message(message_id)
    body = result.get("body")
    if isinstance(body, dict) and "content" in body:
        body["content"] = f"<correo_no_confiable>\n{body['content']}\n</correo_no_confiable>"
    return result


async def _generated_attachment(session: AsyncSession, job_id: str) -> Attachment:
    """Carga el documento de un trabajo de doc-gen terminado para adjuntarlo a un correo."""
    try:
        job = await session.get(Job, uuid.UUID(job_id))
    except ValueError as exc:
        raise ValidationFailedError(f"Identificador de trabajo inválido: {job_id}") from exc
    if job is None or job.job_type not in FILE_JOB_TYPES:
        raise NotFoundError(f"No hay ningún documento generado con el trabajo {job_id}")
    if job.status != "completed" or not job.result:
        raise ValidationFailedError(
            f"El documento del trabajo {job_id} todavía no está listo ({job.status})"
        )

    result = job.result
    path = Path(result["storage_path"])
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise NotFoundError(f"El archivo del documento {job_id} ya no existe") from exc
    topic = re.sub(r"\W+", "-", str(result.get("topic") or "")).strip("-")[:60]
    filename = f"{result.get('kind') or 'documento'}-{topic or job_id[:8]}{path.suffix}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Attachment(filename=filename, content=content, mime_type=mime_type)


@router.post("/draft", response_model=EmailDraftResponse, status_code=202)
async def draft(
    payload: EmailDraftRequest,
    confirmation_service: ConfirmationServiceDep,
    session: DbSession,
    settings: SettingsDep,
    # Sin usar aquí: resolverlo hace que el borrador falle ya si el correo no está configurado.
    _backend: MailBackendDep,
) -> EmailDraftResponse:
    """Guarda el borrador y manda a Telegram los botones para aprobarlo. El token no se
    devuelve: solo el botón (plugin jarvis-aprobaciones) puede confirmar el envío."""
    if not payload.to:
        raise ValidationFailedError("El correo debe tener al menos un destinatario")

    summary = f"Correo para {', '.join(payload.to)} — asunto: {payload.subject}"
    attachment_name = None
    if payload.attachment_job_id:
        attachment = await _generated_attachment(session, payload.attachment_job_id)
        attachment_name = attachment.filename
        summary += f" — adjunto: {attachment_name}"
    pending = await confirmation_service.request(
        payload.telegram_user_id,
        action="send_email",
        summary=summary,
        payload=payload.model_dump(),
    )
    minutes = max(1, settings.confirmation_ttl_seconds // 60)
    try:
        await send_approval(
            settings.telegram_bot_token,
            payload.telegram_user_id,
            email_approval_text(payload.model_dump(), attachment_name, minutes),
            pending.token,
        )
    except Exception:
        await confirmation_service.cancel(pending.token)
        raise
    return EmailDraftResponse(summary=pending.summary, expires_at=pending.expires_at)


@router.post("/draft/{token}/cancel")
async def cancel(
    token: str,
    payload: EmailConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    return {"cancelled": True, "subject": pending.payload.get("subject")}


@router.post("/draft/{token}/confirm")
async def confirm(
    token: str,
    payload: EmailConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
    backend: MailBackendDep,
    session: DbSession,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    draft = pending.payload
    attachments = None
    if draft.get("attachment_job_id"):
        attachments = [await _generated_attachment(session, draft["attachment_job_id"])]
    await backend.send_mail(
        to=draft["to"],
        subject=draft["subject"],
        body=draft["body"],
        cc=draft.get("cc") or None,
        attachments=attachments,
    )
    return {"sent": True, "to": draft["to"], "subject": draft["subject"]}
