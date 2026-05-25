import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from prd_engine.models.workflow import IdempotencyKey
from prd_engine.core.config import get_settings
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def hash_key(key: str) -> str:
    """Generate SHA-256 hash of idempotency key."""
    return hashlib.sha256(key.encode()).hexdigest()


def hash_request(request_data: Dict[str, Any]) -> str:
    """Generate hash of request payload for comparison."""
    sorted_json = json.dumps(request_data, sort_keys=True)
    return hashlib.sha256(sorted_json.encode()).hexdigest()


async def check_idempotency(
    session: AsyncSession,
    idempotency_key: str,
) -> Optional[Dict[str, Any]]:
    """
    Check if an idempotency key exists and is still valid.
    Returns cached response if found, None otherwise.
    """
    key_hash = hash_key(idempotency_key)

    result = await session.execute(
        select(IdempotencyKey).where(IdempotencyKey.key_hash == key_hash)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.expires_at > datetime.utcnow():
            logger.info(
                "idempotency_cache_hit",
                key=idempotency_key[:8],
                status_code=existing.status_code,
            )
            return {
                "response": existing.response,
                "status_code": existing.status_code,
                "cached": True,
            }
        else:
            # Expired, will be cleaned up later
            logger.info(
                "idempotency_key_expired",
                key=idempotency_key[:8],
            )

    return None


async def store_idempotency(
    session: AsyncSession,
    idempotency_key: str,
    response: Dict[str, Any],
    status_code: int,
    request_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Store idempotency key with response for future deduplication."""
    key_hash = hash_key(idempotency_key)
    request_hash = hash_request(request_data) if request_data else None
    expires_at = datetime.utcnow() + timedelta(hours=settings.idempotency_ttl_hours)

    idempotency_record = IdempotencyKey(
        key_hash=key_hash,
        original_key=idempotency_key,
        response=response,
        status_code=status_code,
        expires_at=expires_at,
        request_hash=request_hash,
    )

    session.merge(idempotency_record)
    await session.flush()

    logger.info(
        "idempotency_key_stored",
        key=idempotency_key[:8],
        expires_at=expires_at.isoformat(),
    )


async def cleanup_expired_idempotency_keys(session: AsyncSession) -> int:
    """Remove expired idempotency keys from database."""
    from sqlalchemy import delete

    result = await session.execute(
        delete(IdempotencyKey).where(IdempotencyKey.expires_at < datetime.utcnow())
    )
    deleted_count = result.rowcount or 0

    if deleted_count > 0:
        logger.info("idempotency_cleanup", deleted_count=deleted_count)

    return deleted_count
