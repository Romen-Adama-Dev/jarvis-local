from typing import Any

from qdrant_client import AsyncQdrantClient

from apps.worker.jarvis_worker.settings import redis_settings
from apps.worker.jarvis_worker.tasks import (
    deep_rag_query,
    delete_document,
    ingest_document,
    reindex_document,
)
from packages.core.db.session import make_engine, make_session_factory
from packages.core.logging import configure_logging, get_logger
from packages.core.settings import get_settings
from packages.inference.airllm import AirLLMProvider
from packages.inference.ollama import OllamaProvider
from packages.inference.router import InferenceMode, InferenceRouter
from packages.rag.embeddings import FastEmbedProvider
from packages.rag.orchestrator import HybridRagOrchestrator

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    ctx["qdrant_client"] = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    ctx["qdrant_collection"] = settings.qdrant_collection
    cache_dir = str(settings.jarvis_models_dir / "fastembed")
    ctx["embedding_provider"] = FastEmbedProvider(cache_dir=cache_dir)
    if settings.airllm_enabled:
        airllm_provider = AirLLMProvider(
            settings.airllm_service_url,
            settings.airllm_model,
            timeout_seconds=settings.airllm_timeout_seconds,
        )
        ctx["airllm_provider"] = airllm_provider
        ctx["deep_orchestrator"] = HybridRagOrchestrator(
            ctx["qdrant_client"],
            settings.qdrant_collection,
            ctx["embedding_provider"],
            InferenceRouter(providers={InferenceMode.DEEP: airllm_provider}),
        )
        if settings.airllm_release_ollama_vram:
            ctx["ollama_provider"] = OllamaProvider(
                settings.ollama_host, settings.ollama_primary_model
            )
    logger.info("worker_started", airllm_enabled=settings.airllm_enabled)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    airllm_provider = ctx.get("airllm_provider")
    if airllm_provider is not None:
        await airllm_provider.aclose()
    ollama_provider = ctx.get("ollama_provider")
    if ollama_provider is not None:
        await ollama_provider.aclose()
    await ctx["engine"].dispose()
    await ctx["qdrant_client"].close()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [ingest_document, delete_document, reindex_document, deep_rag_query]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()
    max_jobs = 1
    job_timeout = 7500
