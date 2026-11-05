import hashlib
import json
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from prd_engine.api.middleware.idempotency import check_idempotency, store_idempotency
from prd_engine.db.database import AsyncSessionLocal
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache successful API responses for requests carrying an idempotency key."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        if "/health" in request.url.path or not request.url.path.startswith("/api"):
            return await call_next(request)

        body = await request.body()
        try:
            request_data = json.loads(body.decode())
            if not isinstance(request_data, dict):
                request_data = {"_body": request_data}
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_data = {"_raw_body_sha256": hashlib.sha256(body).hexdigest()}

        async with AsyncSessionLocal() as session:
            try:
                cached = await check_idempotency(session, idempotency_key, request_data)
                if cached and cached.get("cached"):
                    return JSONResponse(
                        content=cached["response"],
                        status_code=cached["status_code"],
                        headers={"X-Idempotency-Cache": "HIT"},
                    )

                response = await call_next(request)
                # Cache only successful responses; do not replay client or server errors.
                if not 200 <= response.status_code < 300:
                    return response

                body_chunks = []
                async for chunk in response.body_iterator:
                    body_chunks.append(chunk)
                response_body = b"".join(body_chunks)

                try:
                    response_data = json.loads(response_body.decode())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_data = {"raw_body_sha256": hashlib.sha256(response_body).hexdigest()}

                await store_idempotency(
                    session=session,
                    idempotency_key=idempotency_key,
                    response=response_data,
                    status_code=response.status_code,
                    request_data=request_data,
                )
                await session.commit()

                headers = dict(response.headers)
                headers["X-Idempotency-Cache"] = "MISS"
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )
            except Exception:
                await session.rollback()
                raise
