from typing import Callable, Awaitable
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import hmac
import hashlib

from prd_engine.core.config import get_settings
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify webhook signature using HMAC-SHA256.
    
    Args:
        payload: Raw request body bytes
        signature: Signature from X-Webhook-Signature header
        
    Returns:
        True if signature is valid, False otherwise
    """
    expected_signature = hmac.new(
        settings.webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


async def webhook_signature_validator(
    request: Request,
    call_next: Callable[[Request], Awaitable[JSONResponse]],
) -> JSONResponse:
    """
    Middleware to validate webhook signatures for webhook ingestion endpoints.
    """
    # Only validate webhook ingestion endpoint
    if not request.url.path.endswith("/webhooks/ingest"):
        return await call_next(request)

    if request.method != "POST":
        return await call_next(request)

    signature = request.headers.get("X-Webhook-Signature")

    if not signature:
        logger.warning("webhook_missing_signature", path=request.url.path)
        raise HTTPException(
            status_code=401,
            detail="Missing webhook signature. Required header: X-Webhook-Signature",
        )

    # Get raw body for signature verification
    body = await request.body()

    if not verify_webhook_signature(body, signature):
        logger.warning(
            "webhook_invalid_signature",
            path=request.url.path,
            signature_provided=signature[:8] if signature else None,
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    logger.info(
        "webhook_signature_validated",
        path=request.url.path,
    )

    return await call_next(request)
