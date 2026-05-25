from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey, Index, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ENUM as PGENUM
from sqlalchemy.orm import relationship
from prd_engine.db.database import Base
import enum


class WorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowType(str, enum.Enum):
    PRD_PROCESSING = "prd_processing"
    ARCHITECTURE_ANALYSIS = "architecture_analysis"
    VALIDATION = "validation"
    DEPLOYMENT = "deployment"


class WebhookEventType(str, enum.Enum):
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_type = Column(PGENUM(WorkflowType), nullable=False)
    status = Column(PGENUM(WorkflowStatus), nullable=False, default=WorkflowStatus.PENDING)
    priority = Column(Integer, nullable=False, default=5)
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    idempotency_key = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    metadata = Column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_workflows_status", "status"),
        Index("idx_workflows_type", "workflow_type"),
        Index("idx_workflows_created_at", "created_at", postgresql_using="btree", postgresql_ops={"created_at": "DESC"}),
        Index("idx_workflows_priority_status", "priority", "created_at", postgresql_where=(status == "pending")),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key_hash = Column(String(64), primary_key=True)
    original_key = Column(String(255), nullable=False)
    response = Column(JSON, nullable=True)
    status_code = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    request_hash = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_idempotency_expires_at", "expires_at"),
    )


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_type = Column(PGENUM(WebhookEventType), nullable=False)
    payload = Column(JSON, nullable=False)
    signature = Column(String(255), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    processed = Column(Boolean, nullable=False, default=False)
    processing_error = Column(Text, nullable=True)
    workflow_id = Column(PGUUID(as_uuid=True), ForeignKey("workflows.id"), nullable=True)

    __table_args__ = (
        Index("idx_webhooks_received_at", "received_at", postgresql_using="btree", postgresql_ops={"received_at": "DESC"}),
        Index("idx_webhooks_processed", "processed", postgresql_where=(processed == False)),
        Index("idx_webhooks_event_type", "event_type"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(PGUUID(as_uuid=True), nullable=True)
    actor_id = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_logs_resource", "resource_type", "resource_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_created_at", "created_at", postgresql_using="btree", postgresql_ops={"created_at": "DESC"}),
    )


class RetryQueue(Base):
    __tablename__ = "retry_queue"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = Column(PGUUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    attempt = Column(Integer, nullable=False)
    backoff_seconds = Column(Integer, nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_retry_queue_scheduled_at", "scheduled_at", postgresql_where=(scheduled_at > datetime.utcnow())),
    )
