import os

# Provide non-production values so unit tests can import application settings.
# Tests override values as needed; never use these defaults in deployments.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-value-32-chars-minimum")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-value-32-chars-min")
os.environ.setdefault("API_ACCESS_TOKEN", "test-api-access-token-value-32-chars")
