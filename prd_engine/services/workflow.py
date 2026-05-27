from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from prd_engine.models.workflow import (
    Workflow,
    WorkflowStatus,
    WorkflowType,
    Webhook,
    WebhookEventType,
)
from prd_engine.models.schemas import WorkflowUpdate
from prd_engine.observability.logging import get_logger
from prd_engine.db.redis import acquire_lock, release_lock

logger = get_logger(__name__)


class WorkflowService:
    """Service for workflow management and execution."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_workflow(
        self,
        workflow_type: WorkflowType,
        payload: Dict[str, Any],
        priority: int = 5,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """Create a new workflow and persist to database with idempotency protection."""
        # If idempotency key provided, check for existing workflow
        if idempotency_key:
            result = await self.db.execute(
                select(Workflow).where(
                    Workflow.idempotency_key == idempotency_key
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                logger.info(
                    "workflow_creation_idempotent",
                    workflow_id=str(existing.id),
                    idempotency_key=idempotency_key[:8],
                )
                return existing

        workflow = Workflow(
            workflow_type=workflow_type,
            status=WorkflowStatus.PENDING,
            priority=priority,
            payload=payload,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
            max_retries=3,
        )

        self.db.add(workflow)
        await self.db.flush()

        logger.info(
            "workflow_persisted",
            workflow_id=str(workflow.id),
            type=workflow_type.value,
        )

        return workflow

    async def execute_workflow_with_lock(
        self,
        workflow_id: UUID,
        execution_func,
        *args,
        **kwargs,
    ):
        """
        Execute workflow with distributed locking to prevent concurrent execution.
        
        Args:
            workflow_id: ID of the workflow to execute
            execution_func: Async function to execute the workflow
            *args, **kwargs: Arguments to pass to execution_func
            
        Returns:
            Result of execution_func
        """
        lock_acquired = await acquire_lock(
            key=f"workflow:{workflow_id}",
            ttl_seconds=300,  # 5 minute lock for long-running workflows
            timeout_seconds=5,
        )
        
        if not lock_acquired:
            logger.warning(
                "workflow_execution_locked",
                workflow_id=str(workflow_id),
            )
            raise Exception("Workflow is already being executed")
        
        try:
            result = await execution_func(*args, **kwargs)
            return result
        finally:
            await release_lock(key=f"workflow:{workflow_id}")

    async def update_workflow(
        self,
        workflow_id: UUID,
        update_data: WorkflowUpdate,
    ) -> Optional[Workflow]:
        """Update workflow status and result."""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return None

        if update_data.status:
            workflow.status = update_data.status

            if update_data.status == WorkflowStatus.RUNNING and not workflow.started_at:
                workflow.started_at = datetime.utcnow()

            if update_data.status in [
                WorkflowStatus.COMPLETED,
                WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED,
            ]:
                workflow.completed_at = datetime.utcnow()

        if update_data.result is not None:
            workflow.result = update_data.result

        if update_data.error_message:
            workflow.error_message = update_data.error_message

        await self.db.flush()

        return workflow

    async def cancel_workflow(self, workflow_id: UUID) -> bool:
        """Cancel a pending or running workflow."""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return False

        if workflow.status not in [WorkflowStatus.PENDING, WorkflowStatus.RUNNING]:
            return False

        workflow.status = WorkflowStatus.CANCELLED
        workflow.completed_at = datetime.utcnow()

        await self.db.flush()

        logger.info(
            "workflow_cancelled_service",
            workflow_id=str(workflow_id),
        )

        return True

    async def get_workflow(self, workflow_id: UUID) -> Optional[Workflow]:
        """Retrieve a workflow by ID."""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def increment_retry(self, workflow_id: UUID) -> Optional[Workflow]:
        """Increment retry count for a workflow."""
        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            return None

        workflow.retry_count += 1
        workflow.status = WorkflowStatus.PENDING

        await self.db.flush()

        return workflow

    async def can_retry(self, workflow_id: UUID) -> bool:
        """Check if a workflow can be retried."""
        workflow = await self.get_workflow(workflow_id)
        if not workflow:
            return False

        return (
            workflow.status == WorkflowStatus.FAILED
            and workflow.retry_count < workflow.max_retries
        )
