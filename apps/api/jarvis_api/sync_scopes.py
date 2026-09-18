"""Copia el ámbito (empresa/proyecto) de cada documento de PostgreSQL al payload de sus
fragmentos en Qdrant y crea los índices de ámbito. Para instalaciones anteriores al RAG
multiempresa; idempotente:

    docker compose exec api python -m apps.api.jarvis_api.sync_scopes
"""

import asyncio

from qdrant_client import AsyncQdrantClient
from sqlalchemy import select

from packages.core.db.models import Document
from packages.core.db.session import make_engine, make_session_factory
from packages.core.scope import scope_from_metadata
from packages.core.settings import get_settings
from packages.rag.store import ensure_scope_indexes, set_document_scope


async def main() -> None:
    settings = get_settings()
    qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    engine = make_engine(settings)
    try:
        if not await qdrant.collection_exists(settings.qdrant_collection):
            print("Sin colección en Qdrant: nada que sincronizar.")
            return
        await ensure_scope_indexes(qdrant, settings.qdrant_collection)
        async with make_session_factory(engine)() as session:
            documents = (
                await session.execute(select(Document).where(Document.deleted_at.is_(None)))
            ).scalars()
            for document in documents:
                scope = scope_from_metadata(document.doc_metadata)
                await set_document_scope(
                    qdrant, settings.qdrant_collection, str(document.id), scope.payload()
                )
                print(f"{document.filename}: {scope.label()}")
    finally:
        await qdrant.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
