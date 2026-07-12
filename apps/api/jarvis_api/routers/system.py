from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from apps.api.jarvis_api.deps import DbSession, InferenceRouterDep, QdrantDep, RedisDep
from apps.api.jarvis_api.schemas import (
    DependencyStatus,
    HealthResponse,
    ReadyResponse,
)

router = APIRouter(tags=["system"])

API_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=API_VERSION)


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    session: DbSession,
    redis_client: RedisDep,
    qdrant_client: QdrantDep,
    inference_router: InferenceRouterDep,
) -> ReadyResponse:
    dependencies: list[DependencyStatus] = []

    try:
        await session.execute(text("SELECT 1"))
        dependencies.append(DependencyStatus(name="postgres", healthy=True))
    except Exception as exc:
        dependencies.append(DependencyStatus(name="postgres", healthy=False, detail=str(exc)))

    try:
        pong = await redis_client.ping()
        dependencies.append(DependencyStatus(name="redis", healthy=bool(pong)))
    except Exception as exc:
        dependencies.append(DependencyStatus(name="redis", healthy=False, detail=str(exc)))

    try:
        await qdrant_client.get_collections()
        dependencies.append(DependencyStatus(name="qdrant", healthy=True))
    except Exception as exc:
        dependencies.append(DependencyStatus(name="qdrant", healthy=False, detail=str(exc)))

    for name, health_result in (await inference_router.health_all()).items():
        dependencies.append(
            DependencyStatus(
                name=f"inference:{name}",
                healthy=health_result.healthy,
                detail=health_result.detail,
            )
        )

    all_healthy = all(dep.healthy for dep in dependencies)
    return ReadyResponse(ready=all_healthy, dependencies=dependencies)


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
