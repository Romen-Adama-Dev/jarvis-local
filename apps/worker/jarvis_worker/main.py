from typing import Any

from qdrant_client import AsyncQdrantClient

from apps.worker.jarvis_worker.settings import redis_settings
from apps.worker.jarvis_worker.tasks import (
    delete_document,
    generate_document,
    ingest_document,
    meeting_minutes,
    reindex_document,
)
from packages.core.db.session import make_engine, make_session_factory
from packages.core.logging import configure_logging, get_logger
from packages.core.settings import get_settings
from packages.inference.ollama import OllamaProvider
from packages.inference.router import InferenceMode, InferenceRouter
from packages.rag.embeddings import FastEmbedProvider
from packages.rag.orchestrator import HybridRagOrchestrator
from packages.rag.reranker import FastEmbedReranker

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["settings"] = settings
    engine = make_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    ctx["qdrant_client"] = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    ctx["qdrant_collection"] = settings.qdrant_collection
    cache_dir = str(settings.jarvis_models_dir / "fastembed")
    ctx["embedding_provider"] = FastEmbedProvider(cache_dir=cache_dir)

    docgen_ollama_provider = OllamaProvider(
        settings.ollama_host,
        settings.ollama_primary_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    ctx["docgen_ollama_provider"] = docgen_ollama_provider
    # Cada bloque de un acta son ~8.000 tokens de transcripción: más margen que el chat.
    ctx["meetings_llm"] = OllamaProvider(
        settings.ollama_host, settings.ollama_primary_model, timeout_seconds=900
    )
    docgen_reranker = (
        FastEmbedReranker(cache_dir=cache_dir, model_name=settings.rag_reranker_model)
        if settings.rag_reranker_enabled
        else None
    )
    ctx["rag_orchestrator"] = HybridRagOrchestrator(
        ctx["qdrant_client"],
        settings.qdrant_collection,
        ctx["embedding_provider"],
        InferenceRouter(providers={InferenceMode.NORMAL: docgen_ollama_provider}),
        powerful_model=settings.ollama_powerful_model,
        reranker=docgen_reranker,
        translate_queries=settings.rag_query_translation,
    )

    logger.info("worker_started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    for key in ("docgen_ollama_provider", "meetings_llm"):
        provider = ctx.get(key)
        if provider is not None:
            await provider.aclose()
    await ctx["engine"].dispose()
    await ctx["qdrant_client"].close()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [
        ingest_document,
        delete_document,
        reindex_document,
        generate_document,
        meeting_minutes,
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()
    max_jobs = 1
    job_timeout = 7500
    health_check_interval = 60
