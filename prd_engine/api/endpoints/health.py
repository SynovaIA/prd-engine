from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from prd_engine.db.database import get_db
from prd_engine.db.redis import get_redis
from prd_engine.core.config import get_settings
from prd_engine.models.schemas import HealthResponse
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Comprehensive health check for all system components.",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """
    Perform comprehensive health check of all system components.
    
    Checks:
    - Database connectivity
    - Redis connectivity
    - Application status
    """
    services_status = {}

    # Check database
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        services_status["database"] = True
    except Exception as e:
        logger.error("health_check_database_failed", error=str(e))
        services_status["database"] = False

    # Check Redis
    try:
        redis_client = await get_redis()
        await redis_client.ping()
        services_status["redis"] = True
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        services_status["redis"] = False

    overall_status = "healthy" if all(services_status.values()) else "degraded"

    if not any(services_status.values()):
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        version=settings.version,
        environment=settings.environment,
        timestamp=datetime.utcnow(),
        services=services_status,
    )


@router.get(
    "/ready",
    summary="Readiness check",
    description="Check if the application is ready to accept traffic.",
)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Readiness probe for Kubernetes/load balancer.
    Returns 200 if ready, 503 if not ready.
    """
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))

        redis_client = await get_redis()
        await redis_client.ping()

        return {"status": "ready"}
    except Exception as e:
        logger.warning("readiness_check_failed", error=str(e))
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready",
        )


@router.get(
    "/live",
    summary="Liveness check",
    description="Simple liveness probe to check if the application is running.",
)
async def liveness_check() -> dict:
    """
    Liveness probe for Kubernetes.
    Returns 200 if the application is running.
    """
    return {"status": "alive"}
