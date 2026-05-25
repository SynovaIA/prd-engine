-- PRD Engine Database Initialization Script

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types
CREATE TYPE workflow_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
CREATE TYPE workflow_type AS ENUM ('prd_processing', 'architecture_analysis', 'validation', 'deployment');
CREATE TYPE webhook_event_type AS ENUM ('workflow.started', 'workflow.completed', 'workflow.failed', 'workflow.cancelled');

-- Workflows table
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_type workflow_type NOT NULL,
    status workflow_status NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 5,
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    idempotency_key VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

-- Indexes for workflows
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_type ON workflows(workflow_type);
CREATE INDEX idx_workflows_created_at ON workflows(created_at DESC);
CREATE INDEX idx_workflows_idempotency_key ON workflows(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_workflows_priority_status ON workflows(priority, created_at) WHERE status = 'pending';

-- Idempotency keys table
CREATE TABLE idempotency_keys (
    key_hash VARCHAR(64) PRIMARY KEY,
    original_key VARCHAR(255) NOT NULL,
    response JSONB,
    status_code INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    request_hash VARCHAR(64)
);

CREATE INDEX idx_idempotency_expires_at ON idempotency_keys(expires_at);

-- Webhooks table
CREATE TABLE webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type webhook_event_type NOT NULL,
    payload JSONB NOT NULL,
    signature VARCHAR(255) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processing_error TEXT,
    workflow_id UUID REFERENCES workflows(id)
);

CREATE INDEX idx_webhooks_received_at ON webhooks(received_at DESC);
CREATE INDEX idx_webhooks_processed ON webhooks(processed) WHERE processed = FALSE;
CREATE INDEX idx_webhooks_event_type ON webhooks(event_type);

-- Audit log table
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    actor_id VARCHAR(255),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- Retry queue table (for persistent retry tracking)
CREATE TABLE retry_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attempt INTEGER NOT NULL,
    backoff_seconds INTEGER NOT NULL,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_retry_queue_scheduled_at ON retry_queue(scheduled_at) WHERE scheduled_at > NOW();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for workflows table
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to clean expired idempotency keys
CREATE OR REPLACE FUNCTION clean_expired_idempotency_keys()
RETURNS void AS $$
BEGIN
    DELETE FROM idempotency_keys WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO prd_engine;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO prd_engine;

COMMENT ON TABLE workflows IS 'Stores workflow execution state and results';
COMMENT ON TABLE idempotency_keys IS 'Stores idempotency keys for request deduplication';
COMMENT ON TABLE webhooks IS 'Stores incoming webhook events';
COMMENT ON TABLE audit_logs IS 'Audit trail for all system actions';
COMMENT ON TABLE retry_queue IS 'Persistent queue for scheduled retries';
