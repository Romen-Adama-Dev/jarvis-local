import asyncio
import dataclasses
import datetime
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import Chunk, Document, Job
from packages.core.jobs import (
    mark_cancelled,
    mark_completed,
    mark_failed,
    mark_progress,
    mark_running,
)
from packages.core.logging import get_logger
from packages.documents.parsers import parse_document
from packages.rag.chunking import chunk_blocks
from packages.rag.store import (
    ChunkPoint,
    delete_by_document,
    ensure_collection,
    new_point_id,
    upsert_chunks,
)

logger = get_logger(__name__)


async def _remove_existing_vectors(
    ctx: dict[str, Any], session: AsyncSession, document_id: uuid.UUID
) -> None:
    await delete_by_document(ctx["qdrant_client"], ctx["qdrant_collection"], str(document_id))
    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await session.commit()


async def _run_ingestion(
    ctx: dict[str, Any], session: AsyncSession, document: Document, job: Job
) -> None:
    content = Path(document.storage_path).read_bytes()

    parsed = parse_document(content, document.content_type, document.filename)
    if not parsed.blocks:
        await mark_failed(
            session, job, "No se pudo extraer contenido del documento (vacío o ilegible)"
        )
        document.status = "failed"
        await session.commit()
        return
    await mark_progress(session, job, 20)

    chunks = chunk_blocks(parsed.blocks)
    if not chunks:
        await mark_failed(session, job, "El documento no produjo fragmentos indexables")
        document.status = "failed"
        await session.commit()
        return

    embeddings = ctx["embedding_provider"]
    texts = [c.text for c in chunks]
    dense_vectors = await embeddings.embed_dense(texts, is_query=False)
    sparse_vectors = await embeddings.embed_sparse(texts)
    await mark_progress(session, job, 60)

    await ensure_collection(
        ctx["qdrant_client"], ctx["qdrant_collection"], embeddings.dense_dimension
    )
    await _remove_existing_vectors(ctx, session, document.id)

    now = datetime.datetime.now(datetime.UTC).isoformat()
    points = []
    chunk_rows = []
    for chunk in chunks:
        point_id = new_point_id()
        points.append(
            ChunkPoint(
                point_id=point_id,
                document_id=str(document.id),
                chunk_id=point_id,
                filename=document.filename,
                content_type=document.content_type,
                page=chunk.page,
                section=chunk.section,
                text=chunk.text,
                created_at=now,
                tags=[],
            )
        )
        chunk_rows.append(
            Chunk(
                document_id=document.id,
                qdrant_point_id=point_id,
                section=chunk.section,
                page=chunk.page,
                content_hash=chunk.content_hash,
                char_count=len(chunk.text),
            )
        )

    await upsert_chunks(
        ctx["qdrant_client"], ctx["qdrant_collection"], points, dense_vectors, sparse_vectors
    )
    await mark_progress(session, job, 90)

    session.add_all(chunk_rows)
    document.page_count = parsed.page_count
    document.status = "indexed"
    await session.commit()

    await mark_completed(session, job, {"chunks_indexed": len(chunks)})
    logger.info("ingest_document_completed", document_id=str(document.id), chunks=len(chunks))


async def ingest_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        document = await session.get(Document, uuid.UUID(document_id))
        if job is None or document is None:
            logger.error("ingest_document_missing_row", document_id=document_id, job_id=job_id)
            return
        await mark_running(session, job)
        try:
            await _run_ingestion(ctx, session, document, job)
        except Exception as exc:
            logger.error(
                "ingest_document_failed", document_id=document_id, job_id=job_id, error=str(exc)
            )
            await mark_failed(session, job, f"Error de ingesta: {exc}")
            document.status = "failed"
            await session.commit()


async def reindex_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    await ingest_document(ctx, document_id, job_id)


VRAM_GUARD_INTERVAL_SECONDS = 20.0


async def _evict_ollama_models(ollama: Any, released: list[str], job_id: str) -> None:
    try:
        for name in await ollama.release_vram():
            if name not in released:
                released.append(name)
    except Exception as exc:
        logger.warning("ollama_release_vram_failed", job_id=job_id, error=str(exc))


async def _vram_guard(
    ollama: Any,
    released: list[str],
    job_id: str,
    interval_seconds: float = VRAM_GUARD_INTERVAL_SECONDS,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await _evict_ollama_models(ollama, released, job_id)


async def deep_rag_query(
    ctx: dict[str, Any],
    job_id: str,
    query: str,
    filters: dict | None = None,
    top_k: int = 8,
) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            logger.error("deep_rag_query_missing_job", job_id=job_id)
            return
        if job.status == "cancelling":
            await mark_cancelled(session, job)
            return
        orchestrator = ctx.get("deep_orchestrator")
        if orchestrator is None:
            await mark_failed(
                session, job, "AirLLM está deshabilitado en el worker (AIRLLM_ENABLED=false)"
            )
            return
        await mark_running(session, job)
        ollama = ctx.get("ollama_provider")
        released: list[str] = []
        guard: asyncio.Task | None = None
        if ollama is not None:
            await _evict_ollama_models(ollama, released, job_id)
            guard = asyncio.create_task(_vram_guard(ollama, released, job_id))
        try:
            try:
                answer = await orchestrator.query(query, deep=True, filters=filters, top_k=top_k)
            except Exception as first_exc:
                logger.warning(
                    "deep_rag_query_retrying",
                    job_id=job_id,
                    error=f"{type(first_exc).__name__}: {first_exc}",
                )
                if ollama is not None:
                    await _evict_ollama_models(ollama, released, job_id)
                answer = await orchestrator.query(query, deep=True, filters=filters, top_k=top_k)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            logger.error("deep_rag_query_failed", job_id=job_id, error=detail)
            await mark_failed(session, job, f"Error en consulta profunda: {detail}")
            return
        finally:
            if guard is not None:
                guard.cancel()
            if ollama is not None and released:
                try:
                    await ollama.warm(released)
                except Exception as exc:
                    logger.warning(
                        "ollama_warm_failed", job_id=job_id, models=released, error=str(exc)
                    )
        await mark_completed(
            session,
            job,
            {
                "query": query,
                "answer": answer.answer,
                "sources": [dataclasses.asdict(s) for s in answer.sources],
                "confidence": answer.confidence,
                "insufficient_evidence": answer.insufficient_evidence,
                "warning": answer.warning,
            },
        )
        logger.info("deep_rag_query_completed", job_id=job_id)


async def delete_document(ctx: dict[str, Any], document_id: str, job_id: str) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        document = await session.get(Document, uuid.UUID(document_id))
        if job is None or document is None:
            logger.error("delete_document_missing_row", document_id=document_id, job_id=job_id)
            return
        await mark_running(session, job)
        try:
            await delete_by_document(ctx["qdrant_client"], ctx["qdrant_collection"], document_id)
            await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            document.deleted_at = datetime.datetime.now(datetime.UTC)
            document.status = "deleted"
            await session.commit()
            await mark_completed(session, job, {"deleted_document_id": document_id})
            logger.info("delete_document_completed", document_id=document_id, job_id=job_id)
        except Exception as exc:
            logger.error(
                "delete_document_failed", document_id=document_id, job_id=job_id, error=str(exc)
            )
            await mark_failed(session, job, f"Error al eliminar: {exc}")
