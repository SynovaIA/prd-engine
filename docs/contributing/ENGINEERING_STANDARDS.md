# Engineering Standards

**Document Classification:** Internal Engineering  
**Version:** 1.0.0  
**Owner:** Engineering Leadership Team

---

## 1. Code Quality Standards

### 1.1 Language Requirements

| Component | Language | Version | Linting |
|-----------|----------|---------|---------|
| API Services | Python | 3.11+ | ruff, black, mypy |
| Frontend | TypeScript | 5.0+ | eslint, prettier |
| Infrastructure | HCL | 1.6+ | tflint, checkov |
| Kubernetes | YAML | - | kubeval, kube-score |
| Workflows | JSON/TypeScript | - | n8n lint |

### 1.2 Code Review Requirements

**All PRs must have**:
- [ ] Passing CI pipeline (tests, linting, security scan)
- [ ] Minimum 1 approver (2 for security-sensitive changes)
- [ ] Linked issue/ticket
- [ ] Description of changes and testing performed
- [ ] Backward compatibility assessment
- [ ] Performance impact analysis (if applicable)

**Review SLA**:
- P0 (security/blocking): 4 hours
- P1 (feature blocking): 24 hours
- P2 (standard): 48 hours
- P3 (minor): 1 week

### 1.3 Testing Requirements

| Test Type | Coverage Target | Tools | Execution |
|-----------|-----------------|-------|-----------|
| Unit Tests | >90% | pytest, jest | On every commit |
| Integration Tests | Critical paths | pytest, supertest | Nightly |
| E2E Tests | Core workflows | Playwright | Pre-deployment |
| Performance Tests | Key endpoints | k6, locust | Weekly |
| Security Tests | OWASP Top 10 | OWASP ZAP, semgrep | On every PR |

**Test Naming Convention**:
```python
def test_<component>_<scenario>_<expected_result>():
    # Example
    def test_workflow_validator_invalid_schema_raises_error():
        ...
```

---

## 2. Development Workflow

### 2.1 Git Branch Strategy

```
main (protected)
  │
  ├── develop (integration branch)
  │     │
  │     ├── feature/PRD-123-add-validation
  │     ├── feature/PRD-456-orchestration-update
  │     └── bugfix/FIX-789-memory-leak
  │
  ├── release/v1.5.0
  │
  └── hotfix/HOTFIX-001-critical-patch
```

**Branch Naming**:
- `feature/<TICKET>-<description>` - New features
- `bugfix/<TICKET>-<description>` - Bug fixes
- `hotfix/<TICKET>-<description>` - Production hotfixes
- `release/v<major>.<minor>.<patch>` - Release branches
- `chore/<description>` - Maintenance tasks

### 2.2 Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Build/config changes
- `security`: Security-related changes

**Example**:
```
feat(validation): add schema consistency checker

Implemented JSON Schema validation for all workflow outputs.
Adds automatic rejection of malformed responses before they
reach downstream services.

Closes PRD-123
Security review: @security-team
```

### 2.3 Pull Request Template

```markdown
## Changes
- Brief description of change 1
- Brief description of change 2

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests passing
- [ ] Manual testing performed (describe)

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings introduced
- [ ] Performance tested (if applicable)

## Screenshots (if UI changes)

## Related Issues
Fixes #123
```

---

## 3. API Design Standards

### 3.1 REST Conventions

**URL Structure**:
```
/api/v1/<resource>/<id>/<subresource>
```

**HTTP Methods**:
| Method | Purpose | Idempotent |
|--------|---------|------------|
| GET | Retrieve resource(s) | Yes |
| POST | Create new resource | No |
| PUT | Replace resource | Yes |
| PATCH | Partial update | No |
| DELETE | Remove resource | Yes |

**Response Format**:
```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "error": null
}
```

**Error Response**:
```json
{
  "data": null,
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid schema format",
    "details": [
      {
        "field": "requirements",
        "issue": "Required field missing"
      }
    ]
  }
}
```

### 3.2 Status Codes

| Code | Usage |
|------|-------|
| 200 | Successful GET, PUT, PATCH |
| 201 | Successful POST (resource created) |
| 204 | Successful DELETE (no content) |
| 400 | Invalid request (validation errors) |
| 401 | Authentication required |
| 403 | Insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (duplicate, version mismatch) |
| 422 | Unprocessable entity (semantic errors) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable |

### 3.3 Versioning

- URL versioning: `/api/v1/`, `/api/v2/`
- Deprecation notice: 6 months minimum
- Sunset header on deprecated endpoints
- Migration guide required for major versions

---

## 4. Database Standards

### 4.1 Schema Design

**Naming Conventions**:
- Tables: `snake_case_plural` (e.g., `workflow_executions`)
- Columns: `snake_case` (e.g., `created_at`)
- Primary keys: `id` (UUID)
- Foreign keys: `<referenced_table>_id` (e.g., `organization_id`)
- Timestamps: `created_at`, `updated_at` (ISO 8601)

**Required Columns**:
```sql
CREATE TABLE example_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,  -- Soft delete
    ...
);
```

### 4.2 Migration Guidelines

**File Naming**:
```
YYYYMMDDHHMMSS_<description>.sql
-- Example: 20240115103000_add_workflow_status_index.sql
```

**Migration Rules**:
- All migrations must be reversible (UP/DOWN)
- No destructive operations without approval
- Backfill data in separate migration
- Test on staging with production-like data volume

**Example**:
```sql
-- UP
ALTER TABLE workflows ADD COLUMN status VARCHAR(50) DEFAULT 'pending';
CREATE INDEX idx_workflows_status ON workflows(status);

-- DOWN
DROP INDEX idx_workflows_status;
ALTER TABLE workflows DROP COLUMN status;
```

### 4.3 Query Performance

- All queries must use prepared statements
- Avoid SELECT * in production code
- Use EXPLAIN ANALYZE for complex queries
- Index foreign keys and frequently filtered columns
- Connection pooling required (pgbouncer)

---

## 5. Observability Standards

### 5.1 Logging

**Format**: Structured JSON
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "service": "api-gateway",
  "trace_id": "abc123def456",
  "span_id": "xyz789",
  "message": "Request processed successfully",
  "context": {
    "method": "POST",
    "path": "/api/v1/workflows",
    "status_code": 201,
    "duration_ms": 145,
    "user_id": "usr_abc123"
  }
}
```

**Log Levels**:
| Level | Usage |
|-------|-------|
| ERROR | Actionable failures, alerts triggered |
| WARN | Recoverable issues, degraded functionality |
| INFO | Business events, user actions |
| DEBUG | Detailed execution info (dev/staging only) |

### 5.2 Metrics

**Standard Metrics** (all services):
```python
# Request metrics
http_requests_total{method, path, status}
http_request_duration_seconds{method, path}

# Business metrics
workflows_created_total{org_id}
workflows_completed_total{status}
inference_tokens_used_total{provider, model}
```

**Metric Naming**:
- Use snake_case
- Include unit in name (seconds, bytes, total)
- Add descriptive labels (not high-cardinality)

### 5.3 Tracing

**Required Spans**:
- HTTP request handling
- Database queries
- External API calls
- Workflow execution steps
- AI inference calls

**Propagation**:
- W3C Trace Context format
- Headers: `traceparent`, `tracestate`
- Sample rate: 10% production, 100% staging

---

## 6. Security Standards

### 6.1 Secure Coding

**Input Validation**:
- Validate all inputs at system boundaries
- Use allowlists over blocklists
- Enforce type constraints (Pydantic schemas)
- Sanitize outputs to prevent XSS

**Authentication**:
- Never store plaintext credentials
- Use Argon2id for password hashing
- Implement rate limiting on auth endpoints
- Require MFA for privileged operations

**Secrets Management**:
- No secrets in code or config files
- Use environment variables or Vault
- Rotate secrets every 90 days
- Audit secret access

### 6.2 Dependency Management

**Approval Process**:
1. Security scan (Snyk/Dependabot)
2. License compatibility check
3. Maintenance status review (last commit <6 months)
4. Community adoption (>100 stars, active issues)

**Update Policy**:
- Patch updates: Automated via Dependabot
- Minor updates: PR review required
- Major updates: Architecture review required

---

## 7. Performance Standards

### 7.1 Latency Budgets

| Endpoint Type | p50 Target | p99 Target | Timeout |
|---------------|------------|------------|---------|
| Simple API | 50ms | 200ms | 1s |
| Complex API | 200ms | 500ms | 5s |
| Workflow Initiation | 100ms | 300ms | 2s |
| File Upload | 500ms | 2s | 30s |
| AI Inference | 1s | 5s | 30s |

### 7.2 Throughput Targets

| Component | Minimum TPS | Scaling Trigger |
|-----------|-------------|-----------------|
| API Gateway | 1000 | CPU >70% |
| Workers | 500 | Queue depth >1000 |
| Database | 5000 writes/s | Connections >80% |
| Cache | 50000 ops/s | Memory >80% |

### 7.3 Resource Limits

```yaml
# Kubernetes resource example
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi
```

---

## 8. Documentation Standards

### 8.1 Code Documentation

**Required**:
- Module-level docstrings
- Function/method docstrings with Args, Returns, Raises
- Complex algorithm explanations
- Public API documentation (OpenAPI/Swagger)

**Example**:
```python
def validate_prd_schema(prd: PRD) -> ValidationResult:
    """
    Validate PRD against enterprise schema requirements.
    
    Performs multi-stage validation including:
    - Schema conformance (JSON Schema)
    - Logical consistency checks
    - Compliance verification
    
    Args:
        prd: PRD object to validate
        
    Returns:
        ValidationResult with pass/fail status and errors
        
    Raises:
        SchemaError: If schema is malformed
        ValidationError: If validation fails
        
    Example:
        >>> result = validate_prd_schema(prd)
        >>> if not result.valid:
        ...     print(result.errors)
    """
```

### 8.2 README Requirements

All repositories must include:
- Project description and purpose
- Quick start instructions
- Development setup guide
- Testing instructions
- Deployment procedure
- Contributing guidelines
- License information

---

## 9. Incident Management

### 9.1 Severity Classification

| Severity | Description | Response | Communication |
|----------|-------------|----------|---------------|
| P0 | Complete outage, data breach | Immediate, all-hands | Executive + customers |
| P1 | Major feature broken | 15 minutes | Status page update |
| P2 | Degraded performance | 1 hour | Internal notification |
| P3 | Minor issue, workaround exists | 4 hours | Team channel |

### 9.2 Post-Mortem Template

```markdown
# Post-Mortem: <Incident Title>

## Summary
Brief description of what happened and impact

## Timeline
- HH:MM - Incident started
- HH:MM - Detected
- HH:MM - Responders engaged
- HH:MM - Mitigation applied
- HH:MM - Resolved

## Root Cause
Technical explanation of what caused the incident

## Impact
- Duration: X minutes
- Affected users: X%
- Failed requests: X
- Data loss: None/Describe

## What Went Well
- Detection worked as expected
- Runbook was accurate
- Team responded quickly

## What Could Be Improved
- Alerting threshold too high
- Runbook missing step 3
- Need better dashboards

## Action Items
| Item | Owner | Due Date | Status |
|------|-------|----------|--------|
| Update alert threshold | @engineer | YYYY-MM-DD | Open |
| Add dashboard panel | @engineer | YYYY-MM-DD | Open |
```

---

## 10. Compliance Checklist

Before production deployment:

- [ ] Security scan passed (no critical/high vulnerabilities)
- [ ] Penetration test completed (annual)
- [ ] Load testing completed (target capacity)
- [ ] Disaster recovery tested
- [ ] Monitoring and alerting configured
- [ ] Runbook updated
- [ ] On-call rotation scheduled
- [ ] Compliance review completed (if applicable)
- [ ] Legal review completed (if customer-facing)
- [ ] Documentation published

---

**END OF STANDARDS**

*Last reviewed: 2024-01-15*  
*Next review: 2024-04-15*  
*Violations must be approved by Engineering VP*
