import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from prd_engine.models.workflow import IdempotencyKey
from prd_engine.core.config import get_settings
from prd_engine.observability.logging import get_logger
from prd_engine.db.redis import acquire_lock, release_lock, check_replay_signature, store_processed_request, get_cached_response

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
    
    Uses Redis for fast lookups with database fallback.
    """
    key_hash = hash_key(idempotency_key)
    
    # First check Redis cache (fast path)
    cached = await get_cached_response(idempotency_key)
    if cached:
        logger.info(
            "idempotency_cache_hit_redis",
            key=idempotency_key[:8],
            status_code=cached.get("status_code"),
        )
        return {
            "response": cached.get("response"),
            "status_code": cached.get("status_code"),
            "cached": True,
        }
    
    # Fallback to database
    result = await session.execute(
        select(IdempotencyKey).where(IdempotencyKey.key_hash == key_hash)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.expires_at > datetime.utcnow():
            logger.info(
                "idempotency_cache_hit_db",
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
    """Store idempotency key with response for future deduplication.
    
    Stores in both Redis (for fast lookups) and database (for persistence).
    """
    key_hash = hash_key(idempotency_key)
    request_hash = hash_request(request_data) if request_data else None
    expires_at = datetime.utcnow() + timedelta(hours=settings.idempotency_ttl_hours)

    # Store in Redis for fast lookups
    await store_processed_request(
        request_id=idempotency_key,
        data={"response": response, "status_code": status_code},
        ttl_seconds=settings.idempotency_ttl_hours * 3600,
    )

    # Store in database for persistence
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


async def execute_with_idempotency(
    session: AsyncSession,
    idempotency_key: str,
    execution_func,
    *args,
    **kwargs,
):
    """
    Execute a function with full idempotency protection.
    
    This is the main entry point for idempotent execution:
    1. Acquire distributed lock to prevent concurrent execution
    2. Check for existing cached response
    3. Execute the function if no cache exists
    4. Store the result for future requests
    5. Release the lock
    
    Args:
        session: Database session
        idempotency_key: Unique key for this request
        execution_func: Async function to execute
        *args, **kwargs: Arguments to pass to execution_func
    
    Returns:
        Tuple of (response_data, status_code, is_cached)
    """
    # Acquire lock to prevent concurrent execution of same request
    lock_acquired = await acquire_lock(
        key=f"idempotent:{idempotency_key}",
        ttl_seconds=30,
        timeout_seconds=10,
    )
    
    if not lock_acquired:
        # Another request is processing - check if we can return cached result
        cached = await check_idempotency(session, idempotency_key)
        if cached:
            return cached["response"], cached["status_code"], True
        
        # Still processing, return conflict
        logger.warning(
            "idempotency_concurrent_request",
            key=idempotency_key[:8],
        )
        raise Exception("Concurrent request in progress")
    
    try:
        # Double-check cache after acquiring lock (another request may have completed)
        cached = await check_idempotency(session, idempotency_key)
        if cached:
            return cached["response"], cached["status_code"], True
        
        # Execute the actual function
        response, status_code = await execution_func(*args, **kwargs)
        
        # Store for future idempotent requests
        await store_idempotency(
            session=session,
            idempotency_key=idempotency_key,
            response=response,
            status_code=status_code,
        )
        
        return response, status_code, False
        
    finally:
        # Always release the lock
        await release_lock(key=f"idempotent:{idempotency_key}")
