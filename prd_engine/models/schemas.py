from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class WorkflowStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowTypeEnum(str, Enum):
    PRD_PROCESSING = "prd_processing"
    ARCHITECTURE_ANALYSIS = "architecture_analysis"
    VALIDATION = "validation"
    DEPLOYMENT = "deployment"


class WebhookEventTypeEnum(str, Enum):
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"


class WorkflowCreate(BaseModel):
    workflow_type: WorkflowTypeEnum
    priority: int = Field(default=5, ge=1, le=10)
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None, max_length=255)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowUpdate(BaseModel):
    status: Optional[WorkflowStatusEnum] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: UUID
    workflow_type: WorkflowTypeEnum
    status: WorkflowStatusEnum
    priority: int
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    retry_count: int
    idempotency_key: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    workflows: List[WorkflowResponse]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: datetime
    services: Dict[str, bool]


class WebhookIngestRequest(BaseModel):
    event_type: WebhookEventTypeEnum
    payload: Dict[str, Any]
    signature: str


class RetryRequest(BaseModel):
    workflow_id: UUID
    force: bool = False


class IdempotencyResponse(BaseModel):
    key: str
    cached: bool
    response: Optional[Dict[str, Any]]
    status_code: Optional[int]
