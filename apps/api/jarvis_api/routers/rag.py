from fastapi import APIRouter

from apps.api.jarvis_api.deps import DbSession, RagOrchestratorDep, SettingsDep
from apps.api.jarvis_api.queue import get_arq_pool
from apps.api.jarvis_api.schemas import (
    JobResponse,
    RagQueryRequest,
    RagQueryResponse,
    SourceRef,
)
from apps.api.jarvis_api.scoping import resolve_scope, scoped_filters
from packages.core.db.models import Job
from packages.core.errors import ProviderUnavailableError
from packages.rag.orchestrator import RagAnswer

router = APIRouter(prefix="/v1/rag", tags=["rag"])


def _to_response(result: RagAnswer) -> RagQueryResponse:
    return RagQueryResponse(
        answer=result.answer,
        sources=[
            SourceRef(
                document_id=s.document_id,
                filename=s.filename,
                page=s.page,
                section=s.section,
                chunk_id=s.chunk_id,
                score=s.score,
            )
            for s in result.sources
        ],
        confidence=result.confidence,
        insufficient_evidence=result.insufficient_evidence,
        warning=result.warning,
    )


@router.post("/query", response_model=RagQueryResponse)
async def query(
    payload: RagQueryRequest, orchestrator: RagOrchestratorDep, session: DbSession
) -> RagQueryResponse:
    scope = await resolve_scope(session, payload.company, payload.project)
    result = await orchestrator.query(
        payload.query,
        deep=False,
        filters=scoped_filters(payload.filters, scope),
        top_k=payload.top_k,
    )
    return _to_response(result)


@router.post("/deep-query", response_model=JobResponse, status_code=202)
async def deep_query(
    payload: RagQueryRequest, session: DbSession, settings: SettingsDep
) -> JobResponse:
    if not settings.airllm_enabled:
        raise ProviderUnavailableError(
            "El modo profundo (AirLLM) está deshabilitado en este despliegue "
            "(AIRLLM_ENABLED=false)"
        )
    scope = await resolve_scope(session, payload.company, payload.project)
    job = Job(job_type="deep_query", status="queued", result={"query": payload.query})
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_arq_pool()
    await pool.enqueue_job(
        "deep_rag_query",
        str(job.id),
        payload.query,
        scoped_filters(payload.filters, scope),
        payload.top_k,
    )
    return JobResponse.model_validate(job)
