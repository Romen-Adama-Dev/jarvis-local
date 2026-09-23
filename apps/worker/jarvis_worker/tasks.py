import asyncio
import datetime
import re
import tempfile
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
from packages.core.scope import scope_from_metadata
from packages.docgen.render_docx import render_docx
from packages.docgen.render_markdown import render_markdown
from packages.docgen.render_pdf import render_pdf_via_pandoc
from packages.docgen.render_pptx import render_pptx
from packages.docgen.schema import DocSection, GeneratedDoc
from packages.docgen.templates import build_sections_plan
from packages.documents.parsers import parse_document
from packages.meetings.minutes import (
    build_minutes,
    render_docx_via_pandoc,
    render_minutes_markdown,
)
from packages.meetings.transcribe import format_timestamp, transcribe
from packages.rag.chunking import chunk_blocks
from packages.rag.store import (
    ChunkPoint,
    delete_by_document,
    ensure_collection,
    new_point_id,
    upsert_chunks,
)

DOCGEN_EXTENSIONS = {"md": "md", "docx": "docx", "pptx": "pptx", "pdf": "pdf"}

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
    scope = scope_from_metadata(document.doc_metadata).payload()
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
                company=scope["company"],
                project=scope["project"],
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


def _write_generated_document(doc: GeneratedDoc, fmt: str, out_path: Path) -> None:
    if fmt == "md":
        out_path.write_text(render_markdown(doc), encoding="utf-8")
    elif fmt == "docx":
        render_docx(doc, out_path)
    elif fmt == "pptx":
        render_pptx(doc, out_path)
    elif fmt == "pdf":
        with tempfile.TemporaryDirectory() as tmp_dir:
            markdown_path = Path(tmp_dir) / "source.md"
            markdown_path.write_text(render_markdown(doc), encoding="utf-8")
            render_pdf_via_pandoc(markdown_path, out_path)
    else:
        raise ValueError(f"Formato de documento no soportado: {fmt}")


async def generate_document(
    ctx: dict[str, Any],
    job_id: str,
    kind: str,
    topic: str,
    fmt: str,
    filters: dict | None = None,
) -> None:
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            logger.error("generate_document_missing_job", job_id=job_id)
            return
        if job.status == "cancelling":
            await mark_cancelled(session, job)
            return
        if fmt not in DOCGEN_EXTENSIONS:
            await mark_failed(session, job, f"Formato de documento no soportado: {fmt}")
            return

        orchestrator = ctx["rag_orchestrator"]
        settings = ctx["settings"]
        await mark_running(session, job)
        try:
            sections_plan = build_sections_plan(kind, topic)
            total = len(sections_plan)
            # Las secciones son independientes: se responden en paralelo (acotado por
            # DOCGEN_CONCURRENCY, que debe casar con OLLAMA_NUM_PARALLEL) en vez de en serie.
            semaphore = asyncio.Semaphore(max(1, settings.docgen_concurrency))

            async def answer_section(question: str):
                async with semaphore:
                    return await orchestrator.query(question, filters=filters, top_k=6)

            tasks = [asyncio.create_task(answer_section(q)) for _, q in sections_plan]
            try:
                for done, finished in enumerate(asyncio.as_completed(tasks), start=1):
                    await finished
                    await mark_progress(session, job, int(done / total * 80))
            finally:
                for task in tasks:
                    task.cancel()
            sections = [
                DocSection(
                    title=title,
                    answer=task.result().answer,
                    sources=list(task.result().sources),
                    insufficient_evidence=task.result().insufficient_evidence,
                )
                for (title, _), task in zip(sections_plan, tasks, strict=True)
            ]

            doc = GeneratedDoc(
                kind=kind,
                topic=topic,
                generated_at=datetime.datetime.now(datetime.UTC).isoformat(),
                sections=sections,
            )

            generated_dir = settings.jarvis_data_dir / "generated"
            generated_dir.mkdir(parents=True, exist_ok=True)
            ext = DOCGEN_EXTENSIONS[fmt]
            out_path = generated_dir / f"{job_id}.{ext}"

            await asyncio.to_thread(_write_generated_document, doc, fmt, out_path)
            await mark_progress(session, job, 100)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            logger.error("generate_document_failed", job_id=job_id, error=detail)
            await mark_failed(session, job, f"Error al generar el documento: {detail}")
            return

        await mark_completed(
            session,
            job,
            {
                "kind": kind,
                "topic": topic,
                "format": fmt,
                "storage_path": str(out_path),
                "filename": out_path.name,
                "sections": [
                    {"title": s.title, "insufficient_evidence": s.insufficient_evidence}
                    for s in doc.sections
                ],
            },
        )
        logger.info("generate_document_completed", job_id=job_id, kind=kind, format=fmt)


def _render_minutes_file(markdown_path: Path, fmt: str, out_path: Path) -> None:
    if fmt == "pdf":
        render_pdf_via_pandoc(markdown_path, out_path)
    elif fmt == "docx":
        render_docx_via_pandoc(markdown_path, out_path)


async def meeting_minutes(
    ctx: dict[str, Any],
    job_id: str,
    audio_path: str,
    project: str,
    title: str,
    meeting_date: str,
    fmt: str,
    company: str = "",
) -> None:
    """Grabación → transcripción (GPU si la hay) → acta estructurada → PDF/Word/Markdown.

    Deja en data/meetings/<job_id>/ el audio, la transcripción, el acta en Markdown (con la
    transcripción como anexo) y el acta en el formato pedido. El resultado del trabajo
    lleva el acta estructurada para crear tareas y riesgos en OpenProject."""
    session_factory = ctx["session_factory"]
    settings = ctx["settings"]
    async with session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            logger.error("meeting_minutes_missing_job", job_id=job_id)
            return
        if job.status == "cancelling":
            await mark_cancelled(session, job)
            return
        await mark_running(session, job)
        meeting_dir = Path(audio_path).parent
        try:
            transcript = await asyncio.to_thread(
                transcribe,
                Path(audio_path),
                model_name=settings.meetings_whisper_model,
                models_dir=settings.jarvis_models_dir,
                device=settings.meetings_whisper_device,
                language=settings.meetings_language,
            )
            if not transcript.segments:
                await mark_failed(session, job, "No se ha reconocido voz en la grabación.")
                return
            (meeting_dir / "transcripcion.txt").write_text(
                transcript.with_timestamps(), encoding="utf-8"
            )
            await mark_progress(session, job, 50)

            async def progress(done: int, total: int) -> None:
                await mark_progress(session, job, 50 + int(done / total * 40))

            minutes = await build_minutes(
                ctx["meetings_llm"],
                transcript.text,
                meeting_date=datetime.date.fromisoformat(meeting_date),
                title=title,
                project=project,
                concurrency=max(1, settings.docgen_concurrency // 2),
                on_progress=progress,
            )
            duration = format_timestamp(transcript.duration_seconds)
            markdown = render_minutes_markdown(
                minutes,
                project=project,
                duration=duration,
                transcript=transcript.with_timestamps(),
            )
            slug = re.sub(r"[^a-z0-9]+", "-", minutes.titulo.lower()).strip("-")[:50] or "reunion"
            markdown_path = meeting_dir / "acta.md"
            markdown_path.write_text(markdown, encoding="utf-8")
            out_path = markdown_path if fmt == "md" else meeting_dir / f"acta.{fmt}"
            await asyncio.to_thread(_render_minutes_file, markdown_path, fmt, out_path)
            await mark_progress(session, job, 100)
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            logger.error("meeting_minutes_failed", job_id=job_id, error=detail)
            await mark_failed(session, job, f"Error al preparar el acta: {detail}")
            return

        await mark_completed(
            session,
            job,
            {
                "project": project,
                "company": company,
                "format": fmt,
                "duration": duration,
                "language": transcript.language,
                "storage_path": str(out_path),
                "filename": f"acta-{minutes.fecha}-{slug}.{fmt}",
                "markdown_path": str(markdown_path),
                "minutes": minutes.to_dict(),
            },
        )
        logger.info(
            "meeting_minutes_completed",
            job_id=job_id,
            actions=len(minutes.acciones),
            risks=len(minutes.riesgos),
        )


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
