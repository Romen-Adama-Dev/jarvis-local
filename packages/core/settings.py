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

    rag_reranker_enabled: bool = True
    # Cross-encoder de FastEmbed. El multilingüe "jinaai/jina-reranker-v2-base-multilingual"
    # ordena mucho mejor en español (y es más rápido), pero su licencia es CC-BY-NC-4.0:
    # solo para uso no comercial. Ver packages/rag/reranker.py.
    rag_reranker_model: str = "BAAI/bge-reranker-base"

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

    airllm_enabled: bool = False
    airllm_service_url: str = "http://127.0.0.1:11500"
    airllm_model: str = "unset-hasta-benchmark"
    airllm_max_concurrency: int = 1
    airllm_timeout_seconds: float = 1800.0
    airllm_release_ollama_vram: bool = True

    telegram_bot_token: str = ""
    telegram_authorized_user_ids: str = ""
    openclaw_gateway_host: str = "127.0.0.1"
    openclaw_gateway_port: int = 8899

    # Correo y calendario (docs/EMAIL.md, docs/CALENDAR.md). "imap" y "caldav"
    # funcionan con cualquier proveedor estándar y contraseña de aplicación
    # (scripts/configure-mail); "msgraph" usa Microsoft Graph y requiere un
    # registro de app en Azure (docs/MSGRAPH.md).
    mail_provider: str = "imap"
    imap_host: str = ""
    imap_port: int = 993
    imap_mailbox: str = "INBOX"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    calendar_provider: str = "caldav"
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""
    caldav_calendar_name: str = ""
    calendar_timezone: str = "Europe/Madrid"
    # CALENDAR_PROVIDER=openproject: proyecto de las reuniones sin proyecto concreto.
    openproject_calendar_project: str = "Agenda"

    # Solo con MAIL_PROVIDER/CALENDAR_PROVIDER=msgraph (docs/MSGRAPH.md).
    # client_id/tenant_id vienen del registro de app Azure AD que hace el
    # propietario a mano (scripts/configure-msgraph).
    msgraph_client_id: str = ""
    msgraph_tenant_id: str = ""
    msgraph_token_cache_path: Path = (
        Path.home() / ".openclaw" / "secrets" / "msgraph_token_cache.json"
    )

    jarvis_api_host: str = "127.0.0.1"
    jarvis_api_port: int = 8000
    jarvis_api_internal_token: str = ""

    max_upload_mb: int = 50
    confirmation_ttl_seconds: int = 600
    # Secciones de un documento generadas a la vez (casar con OLLAMA_NUM_PARALLEL).
    docgen_concurrency: int = 4
    # Actas de reunión (packages/meetings): transcripción con faster-whisper en la GPU si
    # la hay ("auto"), si no en CPU. "large-v3-turbo" tarda ~2 min por hora de audio en
    # GPU; en CPU conviene "small" o "medium" (MEETINGS_WHISPER_MODEL).
    meetings_whisper_model: str = "large-v3-turbo"
    meetings_whisper_device: str = "auto"
    meetings_language: str = "es"
    meetings_max_upload_mb: int = 500
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
