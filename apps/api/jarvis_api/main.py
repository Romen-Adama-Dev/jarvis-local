from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from apps.api.jarvis_api.middleware import CorrelationIdMiddleware
from apps.api.jarvis_api.routers import chat, conversations, documents, jobs, models, rag, system
from apps.api.jarvis_api.security import require_internal_token
from packages.core.errors import JarvisError
from packages.core.ids import get_correlation_id
from packages.core.logging import configure_logging
from packages.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="Jarvis Local API", version="0.1.0")
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(system.router)
    protected = [Depends(require_internal_token)]
    app.include_router(chat.router, dependencies=protected)
    app.include_router(rag.router, dependencies=protected)
    app.include_router(documents.router, dependencies=protected)
    app.include_router(jobs.router, dependencies=protected)
    app.include_router(conversations.router, dependencies=protected)
    app.include_router(models.router, dependencies=protected)

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
