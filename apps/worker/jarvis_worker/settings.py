from arq.connections import RedisSettings

from packages.core.settings import get_settings


def redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings(
        host=settings.redis_host, port=settings.redis_port, database=settings.redis_db
    )
