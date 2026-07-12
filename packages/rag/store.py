import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient, models

from packages.rag.embeddings import SparseVector

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


@dataclass(frozen=True, slots=True)
class ChunkPoint:
    point_id: str
    document_id: str
    chunk_id: str
    filename: str
    content_type: str
    page: int | None
    section: str | None
    text: str
    created_at: str
    tags: list[str]


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    point_id: str
    document_id: str
    chunk_id: str
    filename: str
    page: int | None
    section: str | None
    text: str
    score: float


async def ensure_collection(
    client: AsyncQdrantClient, collection_name: str, dense_dimension: int
) -> None:
    exists = await client.collection_exists(collection_name)
    if exists:
        return
    await client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(
                size=dense_dimension, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
    )


async def upsert_chunks(
    client: AsyncQdrantClient,
    collection_name: str,
    points: list[ChunkPoint],
    dense_vectors: list[list[float]],
    sparse_vectors: list[SparseVector],
) -> None:
    qdrant_points = []
    for point, dense, sparse in zip(points, dense_vectors, sparse_vectors, strict=True):
        qdrant_points.append(
            models.PointStruct(
                id=point.point_id,
                vector={
                    DENSE_VECTOR_NAME: dense,
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=sparse.indices, values=sparse.values
                    ),
                },
                payload={
                    "document_id": point.document_id,
                    "chunk_id": point.chunk_id,
                    "filename": point.filename,
                    "content_type": point.content_type,
                    "page": point.page,
                    "section": point.section,
                    "text": point.text,
                    "created_at": point.created_at,
                    "tags": point.tags,
                },
            )
        )
    await client.upsert(collection_name=collection_name, points=qdrant_points)


async def delete_by_document(
    client: AsyncQdrantClient, collection_name: str, document_id: str
) -> None:
    await client.delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            )
        ),
    )


def _build_filter(filters: dict) -> models.Filter | None:
    conditions: list[models.Condition] = []
    if document_id := filters.get("document_id"):
        conditions.append(
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
        )
    if content_type := filters.get("content_type"):
        conditions.append(
            models.FieldCondition(key="content_type", match=models.MatchValue(value=content_type))
        )
    if tags := filters.get("tags"):
        conditions.append(models.FieldCondition(key="tags", match=models.MatchAny(any=tags)))
    if not conditions:
        return None
    return models.Filter(must=conditions)


async def hybrid_search(
    client: AsyncQdrantClient,
    collection_name: str,
    dense_vector: list[float],
    sparse_vector: SparseVector,
    *,
    top_k: int,
    filters: dict | None = None,
    prefetch_limit: int = 40,
) -> list[RetrievedChunk]:
    query_filter = _build_filter(filters or {})

    results = await client.query_points(
        collection_name=collection_name,
        prefetch=[
            models.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=prefetch_limit,
                filter=query_filter,
            ),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vector.indices, values=sparse_vector.values
                ),
                using=SPARSE_VECTOR_NAME,
                limit=prefetch_limit,
                filter=query_filter,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )

    chunks: list[RetrievedChunk] = []
    for point in results.points:
        payload = point.payload or {}
        chunks.append(
            RetrievedChunk(
                point_id=str(point.id),
                document_id=payload.get("document_id", ""),
                chunk_id=payload.get("chunk_id", ""),
                filename=payload.get("filename", ""),
                page=payload.get("page"),
                section=payload.get("section"),
                text=payload.get("text", ""),
                score=point.score,
            )
        )
    return chunks


def new_point_id() -> str:
    return str(uuid.uuid4())
