from datetime import datetime
from typing import List, Tuple, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from prd_engine.models.workflow import Webhook, WebhookEventType
from prd_engine.observability.logging import get_logger

logger = get_logger(__name__)


class WebhookService:
    """Service for webhook ingestion and processing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_webhook(
        self,
        event_type: WebhookEventType,
        payload: dict,
        signature: str,
    ) -> Webhook:
        """Store incoming webhook for processing."""
        webhook = Webhook(
            event_type=event_type,
            payload=payload,
            signature=signature,
            processed=False,
        )

        self.db.add(webhook)
        await self.db.flush()

        return webhook

    async def list_webhooks(
        self,
        page: int = 1,
        page_size: int = 20,
        processed: Optional[bool] = None,
    ) -> Tuple[List[Webhook], int]:
        """List webhooks with pagination."""
        query = select(Webhook).order_by(Webhook.received_at.desc())

        if processed is not None:
            query = query.where(Webhook.processed == processed)

        # Get total count
        count_query = select(func.count()).select_from(Webhook)
        if processed is not None:
            count_query = count_query.where(Webhook.processed == processed)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        webhooks = result.scalars().all()

        return webhooks, total

    async def mark_processed(self, webhook_id: UUID) -> bool:
        """Mark a webhook as processed."""
        result = await self.db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()

        if not webhook:
            return False

        webhook.processed = True
        await self.db.flush()

        logger.info(
            "webhook_marked_processed",
            webhook_id=str(webhook_id),
        )

        return True

    async def mark_error(
        self,
        webhook_id: UUID,
        error_message: str,
    ) -> bool:
        """Mark a webhook with processing error."""
        result = await self.db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()

        if not webhook:
            return False

        webhook.processed = True
        webhook.processing_error = error_message
        await self.db.flush()

        logger.warning(
            "webhook_processing_error",
            webhook_id=str(webhook_id),
            error=error_message,
        )

        return True

    async def get_unprocessed_webhooks(
        self,
        limit: int = 100,
    ) -> List[Webhook]:
        """Get unprocessed webhooks for batch processing."""
        result = await self.db.execute(
            select(Webhook)
            .where(Webhook.processed == False)
            .order_by(Webhook.received_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
