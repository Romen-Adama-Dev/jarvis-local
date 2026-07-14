from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIRLLM_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 11500
    model: str = ""
    models_dir: Path = Path("/srv/jarvis/models/airllm")
    device: str = "auto"
    compression: str = ""
    max_seq_len: int = 4096
    max_new_tokens_default: int = 512
    max_new_tokens_limit: int = 2048
    min_free_gb: float = 15.0
    max_model_download_gb: float = 12.0
    generation_timeout_seconds: float = 1800.0
    queue_max_pending: int = 2
    log_level: str = "info"


@lru_cache
def get_service_settings() -> ServiceSettings:
    return ServiceSettings()
