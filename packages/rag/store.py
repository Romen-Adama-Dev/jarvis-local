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
    # Ámbito (packages/core/scope.py): identificadores de empresa y proyecto, o None.
    company: str | None = None
    project: str | None = None


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
    # Empresa del documento (None = documentación general).
    company: str | None = None


async def ensure_collection(
    client: AsyncQdrantClient, collection_name: str, dense_dimension: int
) -> None:
    if not await client.collection_exists(collection_name):
        await client.create_collection(
            collection_name=collection_name,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=dense_dimension, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={SPARSE_VECTOR_NAME: models.SparseVectorParams()},
        )
    await ensure_scope_indexes(client, collection_name)


async def ensure_scope_indexes(client: AsyncQdrantClient, collection_name: str) -> None:
    """Índices de ámbito. `company` como tenant: Qdrant agrupa en disco los puntos de cada
    empresa y las búsquedas filtradas por empresa rinden como colecciones separadas, sin
    duplicar el índice (multitenancy por payload). Idempotente."""
    info = await client.get_collection(collection_name)
    existing = info.payload_schema or {}
    if "company" not in existing:
        await client.create_payload_index(
            collection_name,
            "company",
            field_schema=models.KeywordIndexParams(
                type=models.KeywordIndexType.KEYWORD, is_tenant=True
            ),
        )
    for field in ("project", "document_id"):
        if field not in existing:
            await client.create_payload_index(
                collection_name, field, field_schema=models.PayloadSchemaType.KEYWORD
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
                    "company": point.company,
                    "project": point.project,
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


async def set_document_scope(
    client: AsyncQdrantClient, collection_name: str, document_id: str, payload: dict
) -> None:
    """Cambia empresa/proyecto de todos los fragmentos de un documento sin reindexarlo."""
    await client.set_payload(
        collection_name=collection_name,
        payload=payload,
        points=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            )
        ),
    )


def _is_empty(key: str) -> models.IsEmptyCondition:
    return models.IsEmptyCondition(is_empty=models.PayloadField(key=key))


def _match(key: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def scope_filter(company_id: str, project_id: str, *, own_only: bool = False) -> models.Filter:
    """Qué documentos ve una consulta: los globales siempre; los de la empresa (sin
    proyecto) si hay empresa; los del proyecto si hay proyecto. Nunca los de otra empresa
    ni los de otro proyecto. `own_only` quita los globales (búsqueda solo en lo propio)."""
    visible: list[models.Condition] = [] if own_only and company_id else [_is_empty("company")]
    if company_id and project_id:
        visible += [
            models.Filter(must=[_match("company", company_id), _is_empty("project")]),
            models.Filter(must=[_match("company", company_id), _match("project", project_id)]),
        ]
    elif company_id:
        visible.append(_match("company", company_id))
    return models.Filter(should=visible)


def _build_filter(filters: dict) -> models.Filter | None:
    conditions: list[models.Condition] = []
    if "scope" in filters:
        scope = filters["scope"] or {}
        conditions.append(
            scope_filter(
                scope.get("company", ""),
                scope.get("project", ""),
                own_only=bool(scope.get("own_only")),
            )
        )
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
                company=payload.get("company"),
            )
        )
    return chunks


def new_point_id() -> str:
    return str(uuid.uuid4())
