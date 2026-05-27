from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application configuration with environment variable support."""

    # Application
    app_name: str = "PRD Engine"
    version: str = "1.0.0"
    environment: str = "production"
    api_prefix: str = "/api/v1"

    # Logging
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://prd_engine:secure_password@localhost:5432/prd_engine"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str
    webhook_secret: str = "webhook-secret-key"

    # Retry Configuration
    max_retries: int = 3
    retry_backoff_base: int = 2

    # Idempotency
    idempotency_ttl_hours: int = 24
    
    # Lock Configuration
    lock_ttl_seconds: int = 30
    lock_timeout_seconds: int = 10
    
    # Replay Protection
    replay_protection_ttl_seconds: int = 3600

    # Worker Mode
    worker_mode: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
