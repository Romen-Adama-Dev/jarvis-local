from fastapi import APIRouter

from apps.api.jarvis_api.deps import DbSession, RagOrchestratorDep
from apps.api.jarvis_api.schemas import RagQueryRequest, RagQueryResponse, SourceRef
from apps.api.jarvis_api.scoping import resolve_scope, scoped_filters
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
        filters=scoped_filters(payload.filters, scope, payload.methodologies),
        top_k=payload.top_k,
    )
    return _to_response(result)
