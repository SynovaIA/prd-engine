from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from datetime import datetime

from prd_engine.db.database import get_db
from prd_engine.models.workflow import Workflow, WorkflowStatus, WorkflowType
from prd_engine.models.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowUpdate,
)
from prd_engine.services.workflow import WorkflowService
from prd_engine.observability.logging import get_logger
from prd_engine.api.middleware.idempotency import check_idempotency

logger = get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workflow",
    description="Initiate a new workflow execution with specified type and payload.",
)
async def create_workflow(
    workflow_data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
) -> WorkflowResponse:
    """
    Create and queue a new workflow for execution.
    
    Supports idempotent requests via X-Idempotency-Key header.
    """
    # Check idempotency if key provided
    if workflow_data.idempotency_key:
        cached = await check_idempotency(db, workflow_data.idempotency_key)
        if cached and cached.get("cached"):
            return WorkflowResponse(**cached["response"])

    service = WorkflowService(db)
    workflow = await service.create_workflow(
        workflow_type=workflow_data.workflow_type,
        payload=workflow_data.payload,
        priority=workflow_data.priority,
        idempotency_key=workflow_data.idempotency_key,
        metadata=workflow_data.metadata,
    )

    logger.info(
        "workflow_created",
        workflow_id=str(workflow.id),
        workflow_type=workflow.workflow_type.value,
        priority=workflow.priority,
    )

    return WorkflowResponse.model_validate(workflow)


@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="List workflows",
    description="Retrieve paginated list of workflows with optional filtering.",
)
async def list_workflows(
    page: int = 1,
    page_size: int = 20,
    status_filter: WorkflowStatus = None,
    workflow_type: WorkflowType = None,
    db: AsyncSession = Depends(get_db),
) -> WorkflowListResponse:
    """
    List workflows with pagination and optional filters.
    """
    query = select(Workflow)

    if status_filter:
        query = query.where(Workflow.status == status_filter)

    if workflow_type:
        query = query.where(Workflow.workflow_type == workflow_type)

    query = query.order_by(Workflow.created_at.desc())

    # Get total count
    count_query = select(func.count()).select_from(Workflow)
    if status_filter:
        count_query = count_query.where(Workflow.status == status_filter)
    if workflow_type:
        count_query = count_query.where(Workflow.workflow_type == workflow_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    workflows = result.scalars().all()

    return WorkflowListResponse(
        workflows=[WorkflowResponse.model_validate(w) for w in workflows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow details",
    description="Retrieve detailed information about a specific workflow.",
)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """
    Get detailed information about a specific workflow by ID.
    """
    from uuid import UUID

    try:
        uuid_id = UUID(workflow_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workflow ID format",
        )

    result = await db.execute(select(Workflow).where(Workflow.id == uuid_id))
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    return WorkflowResponse.model_validate(workflow)


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow status",
    description="Update the status and result of a workflow.",
)
async def update_workflow(
    workflow_id: str,
    update_data: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """
    Update workflow status, result, or error message.
    Typically used by workers to report progress.
    """
    from uuid import UUID

    try:
        uuid_id = UUID(workflow_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workflow ID format",
        )

    service = WorkflowService(db)
    workflow = await service.update_workflow(uuid_id, update_data)

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow {workflow_id} not found",
        )

    logger.info(
        "workflow_updated",
        workflow_id=str(workflow.id),
        status=workflow.status.value,
    )

    return WorkflowResponse.model_validate(workflow)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel workflow",
    description="Cancel a pending or running workflow.",
)
async def cancel_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Cancel a workflow that is pending or running.
    """
    from uuid import UUID

    try:
        uuid_id = UUID(workflow_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workflow ID format",
        )

    service = WorkflowService(db)
    success = await service.cancel_workflow(uuid_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow cannot be cancelled (already completed or failed)",
        )

    logger.info(
        "workflow_cancelled",
        workflow_id=workflow_id,
    )
