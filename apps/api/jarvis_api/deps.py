from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

import redis.asyncio as redis_asyncio
from fastapi import Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.jarvis_api.adapters.db_audit import DbAuditSink
from apps.api.jarvis_api.adapters.redis_confirmation import RedisConfirmationStore
from packages.core.db.session import make_engine, make_session_factory
from packages.core.settings import Settings, get_settings
from packages.inference.router import InferenceMode, InferenceRouter
from packages.msgraph.auth import MsGraphAuthenticator, MsGraphTokenStore
from packages.msgraph.client import MsGraphClient
from packages.rag.orchestrator import NotConfiguredRagOrchestrator, RagOrchestrator
from packages.security.audit import AuditService
from packages.security.authz import TelegramAuthorizer
from packages.security.confirmation import ConfirmationService

# Scopes de correo (Fase 3). Fijos por capacidad, no configurables por entorno:
# ver docs/EMAIL.md y docs/MSGRAPH.md.
MSGRAPH_MAIL_SCOPES = ["Mail.Read", "Mail.Send"]


@lru_cache
def _engine():
    return make_engine(get_settings())


@lru_cache
def _session_factory():
    return make_session_factory(_engine())


@lru_cache
def _redis_client() -> redis_asyncio.Redis:
    return redis_asyncio.from_url(get_settings().redis_dsn, decode_responses=True)


@lru_cache
def _qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


@lru_cache
def _msgraph_client() -> MsGraphClient:
    settings = get_settings()
    authenticator = MsGraphAuthenticator(
        settings.msgraph_client_id,
        settings.msgraph_tenant_id,
        MSGRAPH_MAIL_SCOPES,
        token_store=MsGraphTokenStore(settings.msgraph_token_cache_path),
    )
    return MsGraphClient(authenticator.get_token)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with _session_factory()() as session:
        yield session


def get_settings_dep() -> Settings:
    return get_settings()


def get_redis() -> redis_asyncio.Redis:
    return _redis_client()


def get_qdrant() -> AsyncQdrantClient:
    return _qdrant_client()


def get_msgraph_client() -> MsGraphClient:
    return _msgraph_client()


def get_authorizer(settings: Settings = Depends(get_settings_dep)) -> TelegramAuthorizer:
    return TelegramAuthorizer(settings.authorized_telegram_ids)


def get_audit_service(session: AsyncSession = Depends(get_db_session)) -> AuditService:
    return AuditService(DbAuditSink(session))


def get_confirmation_service(
    settings: Settings = Depends(get_settings_dep),
    redis_client: redis_asyncio.Redis = Depends(get_redis),
) -> ConfirmationService:
    return ConfirmationService(
        RedisConfirmationStore(redis_client), settings.confirmation_ttl_seconds
    )


_inference_router: InferenceRouter | None = None


def set_inference_router(router: InferenceRouter) -> None:
    global _inference_router
    _inference_router = router


def get_inference_router() -> InferenceRouter:
    if _inference_router is None:
        return InferenceRouter(providers={})
    return _inference_router


_rag_orchestrator: RagOrchestrator | None = None


def set_rag_orchestrator(orchestrator: RagOrchestrator) -> None:
    global _rag_orchestrator
    _rag_orchestrator = orchestrator


def get_rag_orchestrator() -> RagOrchestrator:
    if _rag_orchestrator is None:
        return NotConfiguredRagOrchestrator()
    return _rag_orchestrator


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RedisDep = Annotated[redis_asyncio.Redis, Depends(get_redis)]
QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant)]
MsGraphClientDep = Annotated[MsGraphClient, Depends(get_msgraph_client)]
InferenceRouterDep = Annotated[InferenceRouter, Depends(get_inference_router)]
RagOrchestratorDep = Annotated[RagOrchestrator, Depends(get_rag_orchestrator)]
AuthorizerDep = Annotated[TelegramAuthorizer, Depends(get_authorizer)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
ConfirmationServiceDep = Annotated[ConfirmationService, Depends(get_confirmation_service)]

__all__ = ["InferenceMode"]
