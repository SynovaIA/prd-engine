from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from prd_engine.db.database import get_db
from prd_engine.services.webhook import WebhookService
from prd_engine.models.schemas import WebhookIngestRequest
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest webhook event",
    description="Receive and process incoming webhook events from external systems.",
)
async def ingest_webhook(
    webhook_data: WebhookIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ingest a webhook event for processing.
    
    Requires X-Webhook-Signature header with HMAC-SHA256 signature.
    The signature is computed over the raw request body using the configured webhook secret.
    
    Example signature computation:
        import hmac, hashlib
        signature = hmac.new(
            b"your-webhook-secret",
            request_body_bytes,
            hashlib.sha256
        ).hexdigest()
    """
    service = WebhookService(db)

    webhook = await service.ingest_webhook(
        event_type=webhook_data.event_type,
        payload=webhook_data.payload,
        signature=webhook_data.signature,
    )

    logger.info(
        "webhook_ingested",
        webhook_id=str(webhook.id),
        event_type=webhook_data.event_type.value,
    )

    return {
        "status": "accepted",
        "webhook_id": str(webhook.id),
        "event_type": webhook_data.event_type.value,
    }


@router.get(
    "",
    summary="List webhook events",
    description="Retrieve recent webhook events with optional filtering.",
)
async def list_webhooks(
    page: int = 1,
    page_size: int = 20,
    processed: bool = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List webhook events with pagination.
    """
    service = WebhookService(db)
    webhooks, total = await service.list_webhooks(
        page=page,
        page_size=page_size,
        processed=processed,
    )

    return {
        "webhooks": [
            {
                "id": str(w.id),
                "event_type": w.event_type.value,
                "received_at": w.received_at.isoformat(),
                "processed": w.processed,
            }
            for w in webhooks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
