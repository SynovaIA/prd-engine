from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
import asyncio

from prd_engine.core.config import get_settings
from prd_engine.observability.logging import get_logger
from prd_engine.db.database import init_db, close_db
from prd_engine.db.redis import close_redis
from prd_engine.api.middleware.idempotency_middleware import IdempotencyMiddleware
from prd_engine.api.middleware.webhook_auth import webhook_signature_validator

logger = get_logger(__name__)
settings = get_settings()


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Enterprise AI execution framework for transforming business requirements into production-ready systems.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Register middleware
    app.middleware("http")(webhook_signature_validator)
    app.add_middleware(IdempotencyMiddleware)

    # Register exception handlers
    register_exception_handlers(app)

    # Register lifespan events
    register_lifespan_events(app)

    # Register routers
    from prd_engine.api.endpoints.health import router as health_router
    from prd_engine.api.endpoints.workflows import router as workflows_router
    from prd_engine.api.endpoints.webhooks import router as webhooks_router

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(workflows_router, prefix=settings.api_prefix)
    app.include_router(webhooks_router, prefix=settings.api_prefix)

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.error(
            "database_error",
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "database_error",
                "detail": "Database operation failed",
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred",
            },
        )


def register_lifespan_events(app: FastAPI) -> None:
    """Register application lifespan event handlers."""

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info(
            "application_startup",
            name=settings.app_name,
            version=settings.version,
            environment=settings.environment,
        )
        await init_db()
        logger.info("database_initialized")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        logger.info("application_shutdown")
        await close_db()
        await close_redis()


# Create application instance
app = create_application()
