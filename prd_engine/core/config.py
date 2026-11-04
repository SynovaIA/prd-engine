from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env."""

    # Application
    app_name: str = "PRD Engine"
    version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    # Logging
    log_level: str = "INFO"

    # Database and Redis: deployment-specific values must be supplied.
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Security: no hard-coded fallback secrets.
    secret_key: str = Field(min_length=32)
    webhook_secret: str = Field(min_length=32)

    # Retry Configuration
    max_retries: int = 3
    retry_backoff_base: int = 2

    # Idempotency
    idempotency_ttl_hours: int = 24

    # Worker Mode
    worker_mode: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
