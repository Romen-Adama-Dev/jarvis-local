import base64
import binascii
import mimetypes
import re
import shutil
import time
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
from apps.api.jarvis_api.schemas import (
    EmailConfirmRequest,
    EmailDraftRequest,
    EmailDraftResponse,
    EmailFileAttachment,
)
from packages.core.attachments import EMAIL_ATTACHMENT_MAX_BYTES, Attachment
from packages.core.db.models import Job
from packages.core.errors import NotFoundError, ValidationFailedError
from packages.core.jobs import FILE_JOB_TYPES
from packages.security.telegram_approval import email_approval_text, send_approval

router = APIRouter(prefix="/v1/email", tags=["email"])

_MAX_TOP = 50
# Adjuntos de borradores pendientes: se borran al enviar o descartar; los de borradores
# que caducaron sin respuesta, al preparar el siguiente pasado este tiempo.
_STORED_MAX_AGE_SECONDS = 24 * 3600


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


def _attachments_dir(settings: Any) -> Path:
    return Path(settings.jarvis_data_dir) / "email-attachments"


def _purge_stale(root: Path) -> None:
    if not root.is_dir():
        return
    cutoff = time.time() - _STORED_MAX_AGE_SECONDS
    for folder in root.iterdir():
        if folder.is_dir() and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)


def _store_file(settings: Any, upload: EmailFileAttachment) -> tuple[Path, str]:
    """Guarda el archivo del borrador hasta que se envíe o se descarte."""
    name = re.sub(r"[\x00-\x1f/\\]", "", Path(upload.filename).name).strip()[:120] or "adjunto"
    if len(upload.content_base64) > EMAIL_ATTACHMENT_MAX_BYTES * 4 // 3 + 4:
        raise ValidationFailedError(_too_big(name))
    try:
        content = base64.b64decode(upload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationFailedError("El adjunto no llegó bien codificado (base64).") from exc
    if not content:
        raise ValidationFailedError(f"El adjunto «{name}» está vacío.")
    if len(content) > EMAIL_ATTACHMENT_MAX_BYTES:
        raise ValidationFailedError(_too_big(name))
    root = _attachments_dir(settings)
    _purge_stale(root)
    folder = root / uuid.uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    path = folder / name
    path.write_bytes(content)
    return path, name


def _human_size(size: int) -> str:
    if size < 1024**2:
        return f"{max(1, size // 1024)} KB"
    return f"{size / 1024**2:.1f} MB".replace(".", ",")


def _too_big(name: str) -> str:
    limit = EMAIL_ATTACHMENT_MAX_BYTES // 1024**2
    return f"«{name}» pasa de {limit} MiB: es demasiado grande para un correo."


def _stored_attachment(settings: Any, draft: dict[str, Any]) -> Attachment:
    path = Path(draft["attachment_path"]).resolve()
    if not path.is_relative_to(_attachments_dir(settings).resolve()):
        raise ValidationFailedError("Adjunto fuera de su directorio.")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise NotFoundError("El adjunto del borrador ya no existe; prepara otro borrador.") from exc
    name = draft.get("attachment_name") or path.name
    mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Attachment(filename=name, content=content, mime_type=mime_type)


def _discard_stored(settings: Any, draft: dict[str, Any]) -> None:
    if not draft.get("attachment_path"):
        return
    folder = Path(draft["attachment_path"]).resolve().parent
    if folder.parent == _attachments_dir(settings).resolve():
        shutil.rmtree(folder, ignore_errors=True)


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

    if payload.attachment_job_id and payload.attachment_file:
        raise ValidationFailedError("Solo un adjunto por correo: attachment_job_id o el archivo.")

    summary = f"Correo para {', '.join(payload.to)} — asunto: {payload.subject}"
    # El archivo no viaja en la confirmación (Redis): se guarda aparte y va su ruta.
    draft_data = payload.model_dump(exclude={"attachment_file"})
    attachment_name = None
    if payload.attachment_job_id:
        attachment = await _generated_attachment(session, payload.attachment_job_id)
        attachment_name = attachment.filename
    elif payload.attachment_file:
        path, name = _store_file(settings, payload.attachment_file)
        draft_data |= {"attachment_path": str(path), "attachment_name": name}
        attachment_name = f"{name} ({_human_size(path.stat().st_size)})"
    if attachment_name:
        summary += f" — adjunto: {attachment_name}"
    try:
        pending = await confirmation_service.request(
            payload.telegram_user_id,
            action="send_email",
            summary=summary,
            payload=draft_data,
        )
    except Exception:
        _discard_stored(settings, draft_data)
        raise
    minutes = max(1, settings.confirmation_ttl_seconds // 60)
    try:
        await send_approval(
            settings.telegram_bot_token,
            payload.telegram_user_id,
            email_approval_text(draft_data, attachment_name, minutes),
            pending.token,
        )
    except Exception:
        await confirmation_service.cancel(pending.token)
        _discard_stored(settings, draft_data)
        raise
    return EmailDraftResponse(
        summary=pending.summary, expires_at=pending.expires_at, attachment=attachment_name
    )


@router.post("/draft/{token}/cancel")
async def cancel(
    token: str,
    payload: EmailConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    _discard_stored(settings, pending.payload)
    return {"cancelled": True, "subject": pending.payload.get("subject")}


@router.post("/draft/{token}/confirm")
async def confirm(
    token: str,
    payload: EmailConfirmRequest,
    confirmation_service: ConfirmationServiceDep,
    backend: MailBackendDep,
    session: DbSession,
    settings: SettingsDep,
) -> dict[str, Any]:
    pending = await confirmation_service.confirm(payload.telegram_user_id, token)
    draft = pending.payload
    attachments = None
    if draft.get("attachment_job_id"):
        attachments = [await _generated_attachment(session, draft["attachment_job_id"])]
    elif draft.get("attachment_path"):
        attachments = [_stored_attachment(settings, draft)]
    await backend.send_mail(
        to=draft["to"],
        subject=draft["subject"],
        body=draft["body"],
        cc=draft.get("cc") or None,
        attachments=attachments,
    )
    _discard_stored(settings, draft)
    return {"sent": True, "to": draft["to"], "subject": draft["subject"]}
