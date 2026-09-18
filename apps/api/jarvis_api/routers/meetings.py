"""Actas de reunión: se sube la grabación y el worker la transcribe y redacta el acta."""

import datetime
import re
import uuid

from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse

from apps.api.jarvis_api.deps import DbSession, SettingsDep
from apps.api.jarvis_api.queue import get_arq_pool
from apps.api.jarvis_api.schemas import JobResponse
from packages.core.db.models import Job
from packages.core.errors import ConflictError, NotFoundError, ValidationFailedError

router = APIRouter(prefix="/v1/meetings", tags=["meetings"])

AUDIO_SUFFIXES = {".ogg", ".oga", ".opus", ".mp3", ".m4a", ".mp4", ".wav", ".webm", ".flac", ".aac"}
MINUTES_FORMATS = {"pdf", "docx", "md"}
_CHUNK = 1024 * 1024


@router.post("", response_model=JobResponse, status_code=202)
async def create_minutes(
    file: UploadFile,
    session: DbSession,
    settings: SettingsDep,
    project: str = "",
    company: str = "",
    title: str = "",
    meeting_date: str = "",
    format: str = "pdf",
    telegram_user_id: int | None = None,
) -> JobResponse:
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    if suffix not in AUDIO_SUFFIXES:
        valid = ", ".join(sorted(AUDIO_SUFFIXES))
        raise ValidationFailedError(f"Formato de audio no soportado ({suffix}). Válidos: {valid}.")
    if format not in MINUTES_FORMATS:
        raise ValidationFailedError(f"Formato de acta no válido: {format} (pdf, docx o md).")
    if meeting_date:
        try:
            datetime.date.fromisoformat(meeting_date)
        except ValueError as exc:
            raise ValidationFailedError("meeting_date debe ser AAAA-MM-DD.") from exc

    job = Job(job_type="meeting_minutes", status="queued", requested_by=telegram_user_id)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    meeting_dir = settings.jarvis_data_dir / "meetings" / str(job.id)
    meeting_dir.mkdir(parents=True, exist_ok=True)
    audio_path = meeting_dir / f"audio{suffix}"
    limit = settings.meetings_max_upload_mb * 1024 * 1024
    written = 0
    with audio_path.open("wb") as out:
        while chunk := await file.read(_CHUNK):
            written += len(chunk)
            if written > limit:
                out.close()
                audio_path.unlink(missing_ok=True)
                job.status = "failed"
                job.error = "Grabación demasiado grande"
                await session.commit()
                raise ValidationFailedError(
                    f"Grabación demasiado grande (> {settings.meetings_max_upload_mb} MB)."
                )
            out.write(chunk)

    pool = await get_arq_pool()
    await pool.enqueue_job(
        "meeting_minutes",
        str(job.id),
        str(audio_path),
        project,
        title,
        meeting_date or datetime.date.today().isoformat(),
        format,
        company,
    )
    return JobResponse.model_validate(job)


def _completed_meeting(job: Job | None) -> Job:
    if job is None or job.job_type != "meeting_minutes":
        raise NotFoundError("Acta no encontrada")
    if job.status != "completed":
        raise ConflictError(f"El acta todavía no está lista: {job.status}")
    return job


@router.get("/{job_id}/markdown")
async def get_minutes_markdown(job_id: uuid.UUID, session: DbSession) -> FileResponse:
    """El acta en Markdown (con la transcripción como anexo), para el vault y el RAG."""
    job = _completed_meeting(await session.get(Job, job_id))
    result = job.result or {}
    name = re.sub(r"[^\w.-]+", "-", result.get("filename", "acta")).rsplit(".", 1)[0]
    return FileResponse(result["markdown_path"], filename=f"{name}.md", media_type="text/markdown")
