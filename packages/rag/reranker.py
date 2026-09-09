import asyncio
from typing import Protocol

from fastembed.rerank.cross_encoder import TextCrossEncoder

# BAAI/bge-reranker-base (MIT, ~1GB): licencia compatible con el MIT del proyecto.
# El modelo multilingüe jinaai/jina-reranker-v2-base-multilingual generaliza mejor
# a español pero es cc-by-nc-4.0 (no comercial) — no usar como default en un repo MIT.
# Estado a 2026-09: verificar catálogo con TextCrossEncoder.list_supported_models()
# antes de asumir que sigue disponible o de cambiarlo por otro.
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"


class RerankerProvider(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, cache_dir: str, *, model_name: str = RERANKER_MODEL_NAME) -> None:
        self._model = TextCrossEncoder(model_name, cache_dir=cache_dir)

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        def _run() -> list[float]:
            return list(self._model.rerank(query, documents))

        return await asyncio.to_thread(_run)
