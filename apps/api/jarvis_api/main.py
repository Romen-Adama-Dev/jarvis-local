import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.jarvis_api.deps import (
    get_inference_router,
    get_qdrant,
    set_inference_router,
    set_rag_orchestrator,
)
from apps.api.jarvis_api.middleware import CorrelationIdMiddleware
from apps.api.jarvis_api.routers import (
    calendar,
    chat,
    conversations,
    documents,
    email,
    jobs,
    meetings,
    models,
    rag,
    system,
)
from apps.api.jarvis_api.security import require_internal_token
from packages.core.errors import JarvisError
from packages.core.ids import get_correlation_id
from packages.core.logging import configure_logging, get_logger
from packages.core.settings import get_settings
from packages.inference.airllm import AirLLMProvider
from packages.inference.base import InferenceProvider
from packages.inference.ollama import OllamaProvider, warm_quietly
from packages.inference.router import InferenceMode, InferenceRouter
from packages.rag.embeddings import FastEmbedProvider
from packages.rag.orchestrator import HybridRagOrchestrator
from packages.rag.reranker import FastEmbedReranker

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    ollama_provider = OllamaProvider(
        settings.ollama_host,
        settings.ollama_primary_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    # Precarga en segundo plano: tras reiniciar el servidor, la primera pregunta ya no
    # espera a que Ollama suba el modelo a la GPU (ni agota el timeout si tarda).
    warm_task = asyncio.create_task(warm_quietly(ollama_provider))
    providers: dict[InferenceMode, InferenceProvider] = {InferenceMode.NORMAL: ollama_provider}
    airllm_provider = None
    if settings.airllm_enabled:
        airllm_provider = AirLLMProvider(
            settings.airllm_service_url,
            settings.airllm_model,
            timeout_seconds=settings.airllm_timeout_seconds,
        )
        providers[InferenceMode.DEEP] = airllm_provider
    set_inference_router(InferenceRouter(providers=providers))
    logger.info(
        "inference_router_ready",
        ollama_model=settings.ollama_primary_model,
        airllm_enabled=settings.airllm_enabled,
    )

    cache_dir = str(settings.jarvis_models_dir / "fastembed")
    embedding_provider = await asyncio.to_thread(FastEmbedProvider, cache_dir=cache_dir)
    reranker = None
    if settings.rag_reranker_enabled:
        reranker = await asyncio.to_thread(
            FastEmbedReranker, cache_dir=cache_dir, model_name=settings.rag_reranker_model
        )
    orchestrator = HybridRagOrchestrator(
        get_qdrant(),
        settings.qdrant_collection,
        embedding_provider,
        get_inference_router(),
        powerful_model=settings.ollama_powerful_model,
        reranker=reranker,
    )
    set_rag_orchestrator(orchestrator)
    logger.info("rag_orchestrator_ready", reranker_enabled=settings.rag_reranker_enabled)
    yield
    warm_task.cancel()
    await ollama_provider.aclose()
    if airllm_provider is not None:
        await airllm_provider.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Jarvis Local API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(system.router)
    protected = [Depends(require_internal_token)]
    app.include_router(chat.router, dependencies=protected)
    app.include_router(rag.router, dependencies=protected)
    app.include_router(documents.router, dependencies=protected)
    app.include_router(jobs.router, dependencies=protected)
    app.include_router(conversations.router, dependencies=protected)
    app.include_router(models.router, dependencies=protected)
    app.include_router(calendar.router, dependencies=protected)
    app.include_router(email.router, dependencies=protected)
    app.include_router(meetings.router, dependencies=protected)

    @app.exception_handler(JarvisError)
    async def jarvis_error_handler(request: Request, exc: JarvisError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "correlation_id": get_correlation_id(),
                "details": exc.details,
            },
        )

    return app


app = create_app()
