"""Application configuration loaded from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DocuMind AI"
    app_env: str = "development"
    secret_key: str = "change-me"

    database_url: str = "postgresql+psycopg://documind:change-me@db:5432/documind"
    redis_url: str = "redis://redis:6379/0"

    storage_dir: str = "/data/storage"
    max_upload_mb: int = 25

    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    validation_tolerance: float = 0.01
    tax_tolerance_pct: float = 0.5
    low_confidence_threshold: float = 0.75

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embeddings_enabled: bool = True

    rate_limit_default: str = "600/minute"
    rate_limit_login: str = "10/minute"
    rate_limit_storage: str | None = None  # defaults to redis_url; "memory://" for tests

    # Run Celery tasks inline (used by tests / no-Redis dev runs)
    celery_eager: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
