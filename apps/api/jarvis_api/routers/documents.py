import hashlib
import uuid

import magic
from fastapi import APIRouter, UploadFile
from sqlalchemy import select

from apps.api.jarvis_api.deps import DbSession, SettingsDep
from apps.api.jarvis_api.queue import get_arq_pool
from apps.api.jarvis_api.schemas import DocumentListResponse, DocumentResponse, JobResponse
from packages.core.db.models import Document, Job
from packages.core.errors import ConflictError, NotFoundError
from packages.security.validation import validate_filename, validate_mime, validate_size

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
async def list_documents(session: DbSession) -> DocumentListResponse:
    stmt = (
        select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return DocumentListResponse(documents=[DocumentResponse.model_validate(r) for r in rows])


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID, session: DbSession) -> DocumentResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Documento no encontrado")
    return DocumentResponse.model_validate(document)


@router.post("", response_model=JobResponse, status_code=202)
async def upload_document(
    session: DbSession,
    settings: SettingsDep,
    file: UploadFile,
    telegram_user_id: int | None = None,
) -> JobResponse:
    safe_name = validate_filename(file.filename or "")
    content = await file.read()
    validate_size(len(content), settings.max_upload_mb)
    detected_mime = magic.from_buffer(content, mime=True)
    validate_mime(detected_mime)

    sha256 = hashlib.sha256(content).hexdigest()

    existing = (
        await session.execute(
            select(Document).where(Document.sha256 == sha256, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "El documento ya existe (duplicado por hash SHA-256)",
            details={"document_id": str(existing.id), "filename": existing.filename},
        )

    settings.jarvis_documents_dir.mkdir(parents=True, exist_ok=True)
    storage_path = settings.jarvis_documents_dir / f"{sha256}_{safe_name}"
    storage_path.write_bytes(content)

    document = Document(
        filename=safe_name,
        storage_path=str(storage_path),
        content_type=detected_mime,
        sha256=sha256,
        size_bytes=len(content),
        status="pending",
        uploaded_by=telegram_user_id,
    )
    session.add(document)
    await session.flush()

    job = Job(
        job_type="ingest", status="queued", document_id=document.id, requested_by=telegram_user_id
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job("ingest_document", str(document.id), str(job.id))

    return JobResponse.model_validate(job)


@router.delete("/{document_id}", status_code=202)
async def delete_document(document_id: uuid.UUID, session: DbSession) -> JobResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Documento no encontrado")

    job = Job(job_type="delete_document", status="queued", document_id=document.id)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job("delete_document", str(document.id), str(job.id))

    return JobResponse.model_validate(job)


@router.post("/{document_id}/reindex", response_model=JobResponse, status_code=202)
async def reindex_document(document_id: uuid.UUID, session: DbSession) -> JobResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Documento no encontrado")

    job = Job(job_type="reindex", status="queued", document_id=document.id)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job("reindex_document", str(document.id), str(job.id))

    return JobResponse.model_validate(job)
