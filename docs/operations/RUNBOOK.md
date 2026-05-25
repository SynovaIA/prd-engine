# Operational Runbook

**Document Classification:** Internal Operations  
**Version:** 1.0.0  
**On-Call Contact:** platform-oncall@synovia.ai

---

## Quick Reference

| Scenario | Severity | Response Time | Escalation |
|----------|----------|---------------|------------|
| Complete Outage | P0 | Immediate | VP Engineering |
| Degraded Performance | P1 | 15 minutes | Engineering Manager |
| Non-Critical Bug | P2 | 4 hours | Team Lead |
| Feature Request | P3 | Next sprint | Product Manager |

---

## 1. System Access

### 1.1 Production Access Protocol

```bash
# SSH via bastion host (MFA required)
ssh -o "ProxyJump bastion.prd-engine.synovia.ai" admin@prod-cluster

# Kubernetes access
aws eks update-kubeconfig --name prd-engine-prod --region us-east-1

# Verify access
kubectl get nodes
```

### 1.2 Database Access

```bash
# PostgreSQL read replica (preferred for queries)
psql -h prod-db-replica.internal -U readonly -d prd_engine

# Primary (write operations only, with approval)
psql -h prod-db-primary.internal -U admin -d prd_engine
```

---

## 2. Common Incident Responses

### 2.1 High Error Rate (>5%)

**Symptoms**: Elevated 5xx responses in Grafana dashboard

**Diagnosis**:
```bash
# Check recent error logs
kubectl logs -l app=api-gateway --since=15m | grep -i error | tail -50

# Review error breakdown by endpoint
curl -s http://prometheus:9090/api/v1/query?query=rate(http_requests_total{status=~"5.."}[5m])

# Check downstream service health
kubectl get pods -n production | grep -v Running
```

**Resolution**:
1. Identify failing component from logs
2. Check circuit breaker status: `curl http://api-gateway/circuit-breakers`
3. If LLM provider failing, enable fallback:
   ```bash
   kubectl set env deployment/inference-service FALLBACK_PROVIDER=gemini
   ```
4. Scale up workers if overloaded:
   ```bash
   kubectl scale deployment worker --replicas=10
   ```
5. Document incident in post-mortem channel

### 2.2 High Latency (p99 >500ms)

**Symptoms**: Slow API responses, user complaints

**Diagnosis**:
```bash
# Check latency histogram
curl -s http://grafana:3000/api/dashboards/uid/latency-overview

# Identify slow endpoints
kubectl top pods -n production | sort -k3 -rn | head -10

# Check database query performance
psql -h prod-db-replica.internal -U readonly -d prd_engine -c \
  "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Resolution**:
1. If database-related:
   - Enable query caching: `redis-cli CONFIG SET maxmemory-policy allkeys-lru`
   - Add read replica if connection pool exhausted
2. If inference-related:
   - Reduce model complexity for non-critical tasks
   - Increase timeout thresholds temporarily
3. If network-related:
   - Check service mesh latency: `istioctl proxy-status`
   - Verify no packet loss between pods

### 2.3 Workflow Stuck in Pending State

**Symptoms**: Workflows not progressing, Temporal dashboard shows backlog

**Diagnosis**:
```bash
# Check Temporal worker health
kubectl logs -l app=temporal-worker --since=10m

# List stuck workflows
tctl --namespace prd_engine workflow list --query "ExecutionStatus='Running'"

# Check task queue depth
redis-cli LLEN workflow_task_queue
```

**Resolution**:
1. Restart stuck workers:
   ```bash
   kubectl rollout restart deployment/temporal-worker
   ```
2. Clear corrupted tasks (with approval):
   ```bash
   redis-cli DEL workflow_task_queue
   ```
3. Replay failed workflows:
   ```bash
   tctl --namespace prd_engine workflow reset --workflow_id <ID> --reset_type FirstDecisionFailed
   ```

### 2.4 Redis Cache Failure

**Symptoms**: Cache miss rate spikes, increased database load

**Diagnosis**:
```bash
# Check Redis cluster status
redis-cli CLUSTER INFO

# Review memory usage
redis-cli INFO memory

# Check for evictions
redis-cli INFO stats | grep evicted
```

**Resolution**:
1. If single node failure:
   - Cluster auto-failover should occur within 30 seconds
   - Verify new primary elected: `redis-cli CLUSTER NODES`
2. If memory exhaustion:
   - Increase maxmemory: `redis-cli CONFIG SET maxmemory 8gb`
   - Clear expired keys: `redis-cli MEMORY PURGE`
3. If complete cluster failure:
   - Restore from latest RDB snapshot
   - Update application config to point to recovery cluster

### 2.5 LLM Provider Outage

**Symptoms**: Inference errors, fallback notifications in Slack

**Diagnosis**:
```bash
# Check provider health endpoints
curl -s https://status.openai.com/api/v2/status.json
curl -s https://status.anthropic.com/api/v2/status.json

# Review fallback activation logs
kubectl logs -l app=inference-service | grep -i fallback
```

**Resolution**:
1. Verify automatic fallback activated
2. If manual intervention needed:
   ```bash
   # Force specific provider
   kubectl set env deployment/inference-service DEFAULT_PROVIDER=gemini
   
   # Or enable multi-provider round-robin
   kubectl set env deployment/inference-service ROUTING_STRATEGY=round_robin
   ```
3. Monitor token budget consumption on fallback provider
4. Communicate ETA for provider resolution to stakeholders

---

## 3. Maintenance Procedures

### 3.1 Database Migration

**Pre-requisites**: 
- Change approval ticket
- Maintenance window scheduled
- Rollback plan documented

**Execution**:
```bash
# 1. Create backup
pg_dump -h prod-db-primary.internal -U admin prd_engine > backup_$(date +%Y%m%d).sql

# 2. Apply migration
cd scripts/migration
./run_migration.sh --environment production --version 2024_01_15

# 3. Verify schema
psql -h prod-db-primary.internal -U admin -d prd_engine -c "\dt"

# 4. Run smoke tests
cd ../../tests/e2e
pytest test_database_compatibility.py
```

**Rollback**:
```bash
# Restore from backup
psql -h prod-db-primary.internal -U admin prd_engine < backup_$(date +%Y%m%d).sql

# Revert migration version
./run_migration.sh --environment production --rollback --version 2024_01_14
```

### 3.2 Certificate Renewal

**Timeline**: Begin 30 days before expiration

**Execution**:
```bash
# Check certificate expiry
kubectl get cert -A -o custom-columns="NAME:.metadata.name,EXPIRY:.status.notAfter"

# Renew certificates
cert-managerctl renew --all

# Verify renewal
kubectl get cert prd-engine-tls -o jsonpath='{.status.notAfter}'
```

### 3.3 Security Patch Deployment

**Process**:
1. Review CVE advisory and affected components
2. Test patch in staging environment
3. Schedule maintenance window (if restart required)
4. Deploy via GitOps:
   ```bash
   git checkout -b security-patch-$(date +%Y%m%d)
   # Update image tags in values.yaml
   git commit -am "Security patch: CVE-XXXX-XXXX"
   git push origin security-patch-$(date +%Y%m%d)
   # Create PR and merge after approval
   ```
5. Monitor for regressions post-deployment

---

## 4. Monitoring Dashboards

### 4.1 Critical Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| System Overview | grafana/d/system-overview | Overall cluster health |
| API Performance | grafana/d/api-latency | Endpoint response times |
| Workflow Status | grafana/d/workflow-metrics | Active/completed workflows |
| Inference Metrics | grafana/d/llm-usage | Token consumption, provider health |
| Database Health | grafana/d/postgres-stats | Connection pool, query performance |
| Business KPIs | grafana/d/business-metrics | PRDs processed, conversion rates |

### 4.2 Key Alerts

| Alert Name | Condition | Runbook Section |
|------------|-----------|-----------------|
| HighErrorRate | error_rate > 5% for 5m | 2.1 |
| HighLatency | p99_latency > 500ms for 10m | 2.2 |
| WorkflowBacklog | pending_workflows > 1000 for 15m | 2.3 |
| RedisMemoryCritical | redis_memory_used > 90% | 2.4 |
| LLMProviderDown | provider_health = unhealthy for 2m | 2.5 |
| DiskSpaceLow | disk_usage > 85% | 5.1 |

---

## 5. Capacity Management

### 5.1 Current Resource Allocation

| Component | CPU Request | Memory Request | Replicas |
|-----------|-------------|----------------|----------|
| API Gateway | 500m | 512Mi | 3 |
| Worker | 1000m | 1Gi | 5 |
| Inference Service | 2000m | 2Gi | 3 |
| Temporal Worker | 500m | 512Mi | 2 |
| PostgreSQL | 4000m | 8Gi | 3 (1 primary, 2 replicas) |
| Redis | 2000m | 4Gi | 6 (cluster) |

### 5.2 Scaling Triggers

| Metric | Scale Up Threshold | Scale Down Threshold |
|--------|-------------------|---------------------|
| CPU Utilization | >70% for 5m | <30% for 15m |
| Memory Utilization | >80% for 5m | <40% for 15m |
| Queue Depth | >1000 tasks | <100 tasks |
| Request Rate | >500 req/s per pod | <100 req/s per pod |

### 5.3 Manual Scaling Commands

```bash
# Scale workers
kubectl scale deployment worker --replicas=<COUNT>

# Scale inference service
kubectl scale deployment inference-service --replicas=<COUNT>

# Adjust HPA parameters
kubectl set hpa worker --cpu-percent=70 --min=3 --max=15
```

---

## 6. Disaster Recovery

### 6.1 RTO/RPO Targets

| Component | RTO | RPO |
|-----------|-----|-----|
| Application Services | 15 minutes | 0 (stateless) |
| PostgreSQL | 30 minutes | 5 minutes |
| Redis | 15 minutes | 1 hour |
| S3 Artifacts | 1 hour | 0 (versioned) |

### 6.2 Failover Procedure

**Database Failover**:
```bash
# Promote replica to primary
aws rds promote-read-replica --db-instance-identifier prd-engine-db-replica-1

# Update connection strings
kubectl set env deployment/api-gateway DATABASE_HOST=new-primary.internal

# Verify application connectivity
kubectl exec -it api-gateway-pod -- pg_isready -h new-primary.internal
```

**Region Failover** (if applicable):
```bash
# Activate DR region
aws route53 change-resource-record-sets --hosted-zone-id ZONE_ID \
  --change-batch file://dr-failover.json

# Verify traffic routing
dig +short prd-engine.synovia.ai
```

### 6.3 Backup Verification

**Weekly Backup Test**:
```bash
# Restore to staging
./scripts/bootstrap/restore-backup.sh --backup-id latest --environment staging

# Run data integrity checks
pytest tests/integration/test_data_consistency.py

# Document results in weekly ops report
```

---

## 7. Communication Templates

### 7.1 Incident Notification (Slack)

```
🚨 **INCIDENT ALERT** 🚨

Severity: P1
Service: PRD Engine - Inference Layer
Impact: Elevated latency on architecture analysis workflows
Started: 2024-01-15 14:32 UTC
Detected By: Automated alert (HighLatency)

Current Status:
- Error rate: 8% (normal: <1%)
- p99 latency: 850ms (normal: <200ms)
- Affected endpoints: /api/v1/analyze/architecture

Investigation:
- LLM provider experiencing degraded performance
- Fallback to secondary provider activated
- Monitoring for improvement

Next Update: 15 minutes

Incident Channel: #incident-2024-01-15-inference
```

### 7.2 Resolution Notification (Slack)

```
✅ **INCIDENT RESOLVED** ✅

Severity: P1
Service: PRD Engine - Inference Layer
Duration: 47 minutes (14:32 - 15:19 UTC)

Root Cause:
- Primary LLM provider API degradation in us-east-1
- Automatic failover delayed due to health check timeout

Resolution:
- Manually forced fallback to Gemini provider
- Reduced health check timeout from 30s to 10s
- Provider restored normal operations at 15:15 UTC

Impact:
- 23 workflows delayed by average 12 minutes
- No data loss or corruption

Follow-up:
- Post-mortem scheduled for 2024-01-16 10:00 UTC
- Action items tracked in JIRA: OPS-1234

Incident Report: [Link to Confluence]
```

---

## 8. Appendix

### 8.1 Useful Commands Reference

```bash
# Pod debugging
kubectl debug -it <pod-name> --image=busybox --target=<container-name>

# Log streaming
kubectl logs -f -l app=<service> --tail=100

# Port forwarding
kubectl port-forward svc/prometheus 9090:9090

# Execute in pod
kubectl exec -it <pod-name> -- /bin/bash

# Resource monitoring
kubectl top nodes
kubectl top pods -n production

# Network debugging
kubectl run netshoot --rm -it --image=nicolaka/netshoot -- bash
```

### 8.2 External Dependencies

| Service | Purpose | Status Page |
|---------|---------|-------------|
| AWS US-East-1 | Infrastructure | status.aws.amazon.com |
| OpenAI | LLM Provider | status.openai.com |
| Anthropic | LLM Provider | status.anthropic.com |
| Google Cloud | LLM Provider | status.cloud.google.com |

---

**END OF RUNBOOK**

*Last reviewed: 2024-01-15*  
*Next review: 2024-04-15*
