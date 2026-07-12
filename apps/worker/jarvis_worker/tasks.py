import datetime
import uuid
from typing import Any

from packages.core.db.models import Document, Job
from packages.core.jobs import mark_completed, mark_failed, mark_running
from packages.core.logging import get_logger

logger = get_logger(__name__)

PENDING_PHASE_MESSAGE = (
    "Pipeline de ingesta pendiente de la Fase 6 (parsers, chunking, embeddings, Qdrant). "
    "El trabajo queda registrado pero no se ha procesado todavía."
)


async def ingest_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        document = await session.get(Document, uuid.UUID(document_id))
        if job is None or document is None:
            logger.error("ingest_document_missing_row", document_id=document_id, job_id=job_id)
            return
        await mark_running(session, job)
        logger.info("ingest_document_pending_phase6", document_id=document_id, job_id=job_id)
        await mark_failed(session, job, PENDING_PHASE_MESSAGE)


async def delete_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        document = await session.get(Document, uuid.UUID(document_id))
        if job is None or document is None:
            logger.error("delete_document_missing_row", document_id=document_id, job_id=job_id)
            return
        await mark_running(session, job)
        document.deleted_at = datetime.datetime.now(datetime.UTC)
        document.status = "deleted"
        await session.commit()
        await mark_completed(session, job, {"deleted_document_id": document_id})
        logger.info("delete_document_completed", document_id=document_id, job_id=job_id)


async def reindex_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        document = await session.get(Document, uuid.UUID(document_id))
        if job is None or document is None:
            logger.error("reindex_document_missing_row", document_id=document_id, job_id=job_id)
            return
        await mark_running(session, job)
        logger.info("reindex_document_pending_phase6", document_id=document_id, job_id=job_id)
        await mark_failed(session, job, PENDING_PHASE_MESSAGE)
