from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "production"
    log_level: str = "info"

    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "jarvis"
    postgres_user: str = "jarvis"
    postgres_password: str

    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "jarvis_documents"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    jarvis_data_dir: Path = Path("/srv/jarvis/data")
    jarvis_documents_dir: Path = Path("/srv/jarvis/documents")
    jarvis_models_dir: Path = Path("/srv/jarvis/models")
    jarvis_backups_dir: Path = Path("/srv/jarvis/backups")
    jarvis_logs_dir: Path = Path("/srv/jarvis/logs")

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_primary_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_powerful_model: str = "llama3.1:8b-instruct-q4_K_M"
    ollama_embedding_model: str = "nomic-embed-text"

    airllm_service_url: str = "http://127.0.0.1:11500"
    airllm_model: str = "unset-hasta-benchmark"
    airllm_max_concurrency: int = 1

    telegram_bot_token: str = ""
    telegram_authorized_user_ids: str = ""
    openclaw_gateway_host: str = "127.0.0.1"
    openclaw_gateway_port: int = 8899

    jarvis_api_host: str = "127.0.0.1"
    jarvis_api_port: int = 8000
    jarvis_api_internal_token: str = ""

    max_upload_mb: int = 50
    confirmation_ttl_seconds: int = 120
    rate_limit_per_minute: int = 30

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_async_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def authorized_telegram_ids(self) -> set[int]:
        raw = self.telegram_authorized_user_ids.strip()
        if not raw:
            return set()
        return {int(v.strip()) for v in raw.split(",") if v.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
