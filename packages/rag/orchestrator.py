from dataclasses import dataclass
from typing import Protocol

from packages.core.errors import ProviderUnavailableError


@dataclass(frozen=True, slots=True)
class RagSource:
    document_id: str
    filename: str
    chunk_id: str
    page: int | None = None
    section: str | None = None
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class RagAnswer:
    answer: str
    sources: list[RagSource]
    confidence: float
    insufficient_evidence: bool
    warning: str | None = None


class RagOrchestrator(Protocol):
    async def query(
        self,
        query: str,
        *,
        deep: bool = False,
        filters: dict | None = None,
        top_k: int = 8,
    ) -> RagAnswer: ...


class NotConfiguredRagOrchestrator:
    async def query(
        self,
        query: str,
        *,
        deep: bool = False,
        filters: dict | None = None,
        top_k: int = 8,
    ) -> RagAnswer:
        raise ProviderUnavailableError(
            "El RAG todavía no está configurado "
            "(pendiente de completar la Fase 6: ingesta, embeddings y recuperación híbrida)."
        )
