import pytest

from packages.rag.orchestrator import _rerank
from packages.rag.store import RetrievedChunk


def _chunk(chunk_id: str, text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        point_id=chunk_id,
        document_id="doc-1",
        chunk_id=chunk_id,
        filename="libro.pdf",
        page=1,
        section=None,
        text=text,
        score=score,
    )


class FakeReranker:
    def __init__(self, scores_by_text: dict[str, float]) -> None:
        self._scores_by_text = scores_by_text
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, documents))
        return [self._scores_by_text[doc] for doc in documents]


@pytest.mark.asyncio
async def test_rerank_reorders_by_cross_encoder_score_not_original_score():
    chunks = [
        _chunk("a", "poco relevante", score=0.9),
        _chunk("b", "muy relevante", score=0.1),
    ]
    reranker = FakeReranker({"poco relevante": 0.1, "muy relevante": 9.5})

    result = await _rerank(reranker, "pregunta", chunks, top_k=8)

    assert [c.chunk_id for c in result] == ["b", "a"]
    # El score original (escala RRF) no se sobreescribe con el logit del reranker.
    assert result[0].score == 0.1


@pytest.mark.asyncio
async def test_rerank_truncates_to_top_k():
    chunks = [_chunk(str(i), f"texto {i}", score=1.0) for i in range(5)]
    reranker = FakeReranker({f"texto {i}": float(i) for i in range(5)})

    result = await _rerank(reranker, "pregunta", chunks, top_k=2)

    assert len(result) == 2
    assert [c.chunk_id for c in result] == ["4", "3"]


@pytest.mark.asyncio
async def test_rerank_skips_call_for_single_chunk():
    chunks = [_chunk("only", "texto único", score=1.0)]
    reranker = FakeReranker({"texto único": 5.0})

    result = await _rerank(reranker, "pregunta", chunks, top_k=8)

    assert result == chunks
    assert reranker.calls == []
