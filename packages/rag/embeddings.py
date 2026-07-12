import asyncio
from dataclasses import dataclass
from typing import Protocol

from fastembed import SparseTextEmbedding, TextEmbedding

DENSE_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
SPARSE_MODEL_NAME = "Qdrant/bm25"
DENSE_DIMENSION = 768


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class EmbeddingProvider(Protocol):
    dense_dimension: int

    async def embed_dense(
        self, texts: list[str], *, is_query: bool = False
    ) -> list[list[float]]: ...

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]: ...


class FastEmbedProvider:
    def __init__(self, cache_dir: str) -> None:
        self._dense = TextEmbedding(DENSE_MODEL_NAME, cache_dir=cache_dir)
        self._sparse = SparseTextEmbedding(SPARSE_MODEL_NAME, cache_dir=cache_dir)
        self.dense_dimension = DENSE_DIMENSION

    async def embed_dense(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        # paraphrase-multilingual-mpnet-base-v2 is symmetric: no query/passage prefix convention.
        def _run() -> list[list[float]]:
            return [vector.tolist() for vector in self._dense.embed(texts)]

        return await asyncio.to_thread(_run)

    async def embed_sparse(self, texts: list[str]) -> list[SparseVector]:
        def _run() -> list[SparseVector]:
            return [
                SparseVector(indices=vector.indices.tolist(), values=vector.values.tolist())
                for vector in self._sparse.embed(texts)
            ]

        return await asyncio.to_thread(_run)
