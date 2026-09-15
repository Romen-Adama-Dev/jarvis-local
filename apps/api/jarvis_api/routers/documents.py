import hashlib
import uuid

import magic
from fastapi import APIRouter, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from apps.api.jarvis_api.deps import DbSession, SettingsDep
from apps.api.jarvis_api.queue import get_arq_pool
from apps.api.jarvis_api.schemas import (
    DocumentListResponse,
    DocumentResponse,
    GenerateDocumentRequest,
    JobResponse,
    ProjectListResponse,
)
from packages.core.db.models import Document, Job
from packages.core.errors import ConflictError, NotFoundError, ValidationFailedError
from packages.docgen.templates import SECTION_TEMPLATES
from packages.security.validation import validate_filename, validate_mime, validate_size

router = APIRouter(prefix="/v1/documents", tags=["documents"])

VALID_DOCGEN_KINDS = set(SECTION_TEMPLATES)
VALID_DOCGEN_FORMATS = {"md", "docx", "pptx", "pdf"}


@router.get("", response_model=DocumentListResponse)
async def list_documents(session: DbSession) -> DocumentListResponse:
    stmt = (
        select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return DocumentListResponse(documents=[DocumentResponse.model_validate(r) for r in rows])


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(session: DbSession) -> ProjectListResponse:
    stmt = (
        select(Document.doc_metadata["project"].astext)
        .where(
            Document.deleted_at.is_(None),
            Document.doc_metadata["project"].astext.isnot(None),
        )
        .distinct()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return ProjectListResponse(projects=sorted(rows))


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
    project: str | None = None,
) -> JobResponse:
    if project is not None:
        project = project.strip()[:128] or None
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
        doc_metadata={"project": project} if project else {},
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


@router.post("/generate", response_model=JobResponse, status_code=202)
async def generate_document(payload: GenerateDocumentRequest, session: DbSession) -> JobResponse:
    if payload.kind not in VALID_DOCGEN_KINDS:
        valid = ", ".join(sorted(VALID_DOCGEN_KINDS))
        raise ValidationFailedError(
            f"Tipo de documento desconocido: '{payload.kind}'. Tipos válidos: {valid}."
        )
    if payload.format not in VALID_DOCGEN_FORMATS:
        valid = ", ".join(sorted(VALID_DOCGEN_FORMATS))
        raise ValidationFailedError(
            f"Formato de documento desconocido: '{payload.format}'. Formatos válidos: {valid}."
        )

    job = Job(
        job_type="generate_document", status="queued", requested_by=payload.telegram_user_id
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job(
        "generate_document",
        str(job.id),
        payload.kind,
        payload.topic,
        payload.format,
        payload.filters,
    )

    return JobResponse.model_validate(job)


@router.get("/generated/{job_id}")
async def get_generated_document(job_id: uuid.UUID, session: DbSession) -> FileResponse:
    job = await session.get(Job, job_id)
    if job is None or job.job_type != "generate_document":
        raise NotFoundError("Documento generado no encontrado")
    if job.status != "completed":
        raise ConflictError(f"El trabajo todavía no ha terminado: {job.status}")

    result = job.result
    return FileResponse(result["storage_path"], filename=result["filename"])
