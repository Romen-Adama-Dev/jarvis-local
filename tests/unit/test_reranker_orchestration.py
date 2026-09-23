import pytest

from packages.rag.orchestrator import (
    HybridRagOrchestrator,
    _merge_by_score,
    _rerank,
    _rerank_bilingual,
)
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


@pytest.mark.asyncio
async def test_bilingual_rerank_scores_each_list_with_its_own_query():
    """El párrafo en inglés se puntúa con la consulta traducida, no con la original."""
    es = [_chunk("pmbok", "acta de constitución", score=0.5)]
    en = [_chunk("snyder", "project charter form", score=0.4), es[0]]
    scores = {
        ("¿acta?", "acta de constitución"): 1.0,
        ("charter?", "project charter form"): 2.0,
        ("charter?", "acta de constitución"): -3.0,
    }

    class PairReranker:
        async def rerank(self, query: str, documents: list[str]) -> list[float]:
            return [scores[(query, doc)] for doc in documents]

    result = await _rerank_bilingual(PairReranker(), [("¿acta?", es), ("charter?", en)], top_k=8)

    # Cada fragmento una vez, con su mejor puntuación (el del PMBOK no baja a -3).
    assert [c.chunk_id for c in result] == ["snyder", "pmbok"]


def test_merge_without_reranker_keeps_best_hybrid_score():
    a = [_chunk("x", "t", score=0.2), _chunk("y", "u", score=0.1)]
    b = [_chunk("x", "t", score=0.3), _chunk("z", "v", score=0.25)]
    assert [(c.chunk_id, c.score) for c in _merge_by_score(a, b)] == [
        ("x", 0.3),
        ("z", 0.25),
        ("y", 0.1),
    ]


class _FakeInference:
    def __init__(self, reply: str | Exception) -> None:
        self._reply = reply

    async def chat(self, mode, messages, **kwargs):
        if isinstance(self._reply, Exception):
            raise self._reply
        return type("R", (), {"text": self._reply})()


def _orchestrator(reply: str | Exception) -> HybridRagOrchestrator:
    return HybridRagOrchestrator(
        None,  # type: ignore[arg-type]
        "c",
        None,  # type: ignore[arg-type]
        _FakeInference(reply),  # type: ignore[arg-type]
        translate_queries=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ('"What does the project charter include?"\n', "What does the project charter include?"),
        ("¿qué lleva el  acta?", None),  # igual que la original: no hay segunda búsqueda
        ("", None),
        ("x" * 500, None),  # el modelo se ha puesto a explicar
        (RuntimeError("ollama caído"), None),  # sin traducción se busca igual
    ],
)
async def test_translate_query(reply, expected):
    assert await _orchestrator(reply)._translate("¿Qué lleva el acta?") == expected
