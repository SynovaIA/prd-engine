from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import hashlib

from prd_engine.api.middleware.idempotency import (
    check_idempotency,
    store_idempotency,
    hash_key,
)
from prd_engine.db.database import AsyncSessionLocal
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware for handling idempotent requests.
    
    Checks for X-Idempotency-Key header and returns cached response
    if the same request was previously processed.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only process POST, PUT, PATCH requests
        if request.method not in ["POST", "PUT", "PATCH"]:
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")

        if not idempotency_key:
            return await call_next(request)

        # Skip health checks and non-API routes
        if "/health" in request.url.path or not request.url.path.startswith("/api"):
            return await call_next(request)

        async with AsyncSessionLocal() as session:
            # Check for existing response
            cached = await check_idempotency(session, idempotency_key)

            if cached and cached.get("cached"):
                logger.info(
                    "idempotent_request_returned",
                    path=request.url.path,
                    key=idempotency_key[:8],
                )
                return JSONResponse(
                    content=cached["response"],
                    status_code=cached["status_code"],
                    headers={"X-Idempotency-Cache": "HIT"},
                )

            # Process request normally
            response = await call_next(request)

            # Only cache successful responses
            if response.status_code < 500:
                # Collect response body
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Parse JSON response
                try:
                    import json
                    response_data = json.loads(body.decode())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_data = {"raw": True}

                # Store for future idempotent requests
                await store_idempotency(
                    session=session,
                    idempotency_key=idempotency_key,
                    response=response_data,
                    status_code=response.status_code,
                )

                # Return response with header
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers) | {"X-Idempotency-Cache": "MISS"},
                    media_type=response.media_type,
                )

            return response
