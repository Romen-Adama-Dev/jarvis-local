from typing import Any

from apps.worker.jarvis_worker.settings import redis_settings
from apps.worker.jarvis_worker.tasks import delete_document, ingest_document, reindex_document
from packages.core.db.session import make_engine, make_session_factory
from packages.core.logging import configure_logging, get_logger
from packages.core.settings import get_settings

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    logger.info("worker_started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    logger.info("worker_stopped")


class WorkerSettings:
    functions = [ingest_document, delete_document, reindex_document]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()
    max_jobs = 1
    job_timeout = 3600
