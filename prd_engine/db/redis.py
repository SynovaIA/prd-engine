import redis.asyncio as redis
from typing import Optional
from prd_engine.core.config import get_settings

settings = get_settings()

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


async def acquire_lock(
    key: str,
    ttl_seconds: int = 30,
    timeout_seconds: int = 10,
) -> bool:
    """
    Acquire a distributed lock using Redis SETNX pattern.
    
    Args:
        key: Lock key (should be unique per resource)
        ttl_seconds: Lock expiration time (prevents deadlocks)
        timeout_seconds: Max time to wait for acquiring lock
    
    Returns:
        True if lock acquired, False otherwise
    """
    redis_conn = await get_redis()
    lock_key = f"lock:{key}"
    
    # Use SET with NX (only if not exists) and PX (expiration in ms)
    acquired = await redis_conn.set(
        lock_key,
        "1",
        nx=True,
        px=ttl_seconds * 1000,
    )
    
    if acquired:
        return True
    
    # If immediate acquisition failed, try with timeout
    import asyncio
    start_time = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start_time < timeout_seconds:
        await asyncio.sleep(0.1)
        acquired = await redis_conn.set(
            lock_key,
            "1",
            nx=True,
            px=ttl_seconds * 1000,
        )
        if acquired:
            return True
    
    return False


async def release_lock(key: str) -> bool:
    """
    Release a distributed lock.
    
    Args:
        key: Lock key to release
    
    Returns:
        True if lock was released, False if it didn't exist
    """
    redis_conn = await get_redis()
    lock_key = f"lock:{key}"
    deleted = await redis_conn.delete(lock_key)
    return deleted > 0


async def check_replay_signature(
    signature: str,
    ttl_seconds: int = 3600,
) -> bool:
    """
    Check if a signature has been seen before (replay attack detection).
    
    Args:
        signature: Unique signature to check
        ttl_seconds: How long to track signatures
    
    Returns:
        True if this is a NEW signature (not a replay),
        False if signature was already seen (replay detected)
    """
    redis_conn = await get_redis()
    sig_key = f"replay:{signature}"
    
    # Try to set the signature - returns True only if key didn't exist
    is_new = await redis_conn.set(
        sig_key,
        "1",
        nx=True,
        px=ttl_seconds * 1000,
    )
    
    return is_new is True


async def store_processed_request(
    request_id: str,
    data: dict,
    ttl_seconds: int = 86400,
) -> None:
    """
    Store processed request data for idempotency checks.
    
    Uses Redis for fast lookups with automatic TTL expiration.
    
    Args:
        request_id: Unique identifier for the request
        data: Response data to cache
        ttl_seconds: Time-to-live for cached data
    """
    redis_conn = await get_redis()
    import json
    key = f"idempotent:{request_id}"
    await redis_conn.setex(
        key,
        ttl_seconds,
        json.dumps(data),
    )


async def get_cached_response(request_id: str) -> Optional[dict]:
    """
    Retrieve cached response for an idempotent request.
    
    Args:
        request_id: Unique identifier for the request
    
    Returns:
        Cached response data or None if not found/expired
    """
    redis_conn = await get_redis()
    import json
    key = f"idempotent:{request_id}"
    cached = await redis_conn.get(key)
    
    if cached:
        return json.loads(cached)
    return None
