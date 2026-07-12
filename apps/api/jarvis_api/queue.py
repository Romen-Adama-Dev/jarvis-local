from arq import ArqRedis
from arq.connections import RedisSettings, create_pool

from packages.core.settings import get_settings

_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(
            RedisSettings(
                host=settings.redis_host, port=settings.redis_port, database=settings.redis_db
            )
        )
    return _pool
