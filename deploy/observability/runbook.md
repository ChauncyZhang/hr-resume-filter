# UX-09 observability runbook

## Reliability contract

The first-release SLIs are API non-5xx request ratio, API request latency,
dependency readiness, oldest runnable job age, and successful private scrape
ratio. The initial 30-day objectives are 99.9% API non-5xx responses, 99% of
API requests below one second, 99.9% successful readiness checks, and 99% of
runnable jobs started within five minutes. `/health/live` is process liveness
only; `/health/ready` is the dependency-aware admission signal.

Metric dimensions are deliberately bounded. Never add trace IDs, UUIDs,
organization or user identifiers, IP addresses, query strings, object keys,
raw errors, or payload values as labels. Trace IDs belong in structured logs
and persisted job attempts, not metrics or Alertmanager annotations.

## Deployment and rollback

1. Provision `OBSERVABILITY_DB_USER` as a login role with `CONNECT`, schema
   `USAGE`, and `SELECT` only on the queue tables and PostgreSQL statistics
   required by postgres-exporter. Store its password outside the repository.
2. Validate the three-file model with base, production, and observability
   Compose files. Confirm the proxy is the only service with a published port.
3. Start Alertmanager, exporters, and Prometheus first. Confirm every private
   target is up, then roll one API instance with the metrics-enabled image.
4. Exercise live, ready, one template route, and a disposable queue item.
   Observe metrics for at least one evaluation interval before enabling alert
   delivery. Route warning notifications before critical paging.

Rollback is defined before rollout: disable notification delivery, stop the
observability-only services, and restore the previous API image. The base and
production Compose files remain independently usable. Do not expose a
monitoring port to work around a private-network scrape failure. Preserve the
Prometheus volume for incident evidence unless data retention itself is the
reason for rollback.

## Common triage

For every alert, first check user impact, deployment changes, and target
freshness. Correlate with a trace ID from a user-visible failure, but never put
that ID into alert labels. If a metric target is stale, repair collection
before drawing conclusions from its last sample.

### ApiHigh5xxRateWarning / ApiHigh5xxRateCritical

Check the failing template routes, readiness results, and the most recent API
deployment. Roll back progressively if failures began with a release. Do not
log request bodies or headers while investigating.

### ApiHighLatencyWarning / ApiHighLatencyCritical

Compare route-template latency with database connections, container CPU, and
storage readiness. Reduce traffic or roll back before raising capacity limits.

### ApiReadinessFailure

Identify the fixed `dependency` label, then check PostgreSQL or MinIO health
from the private network. Liveness remaining green does not make the instance
safe to receive traffic.

### QueueCollectorDown

Check the exporter target, read-only role connectivity, and schema grants.
Never replace the monitoring DSN with owner or application credentials.

### QueueOldestReadyTooOldWarning / QueueOldestReadyTooOldCritical

Check worker liveness, lease churn, job-type backlog, and downstream capacity.
Scale workers gradually only after verifying the dependency can absorb load.

### QueueExpiredLeases

Look for worker restarts, heartbeat delays, and long handlers. Repeated manual
lease repair requires a documented or automated recovery procedure.

### QueueDeadLetters

Review bounded job type and safe error class, then follow the owning workflow's
replay procedure. Never mutate queue state directly without an incident record
and a rollback plan.

### OutboxOldestReadyTooOld

Check dispatcher health and downstream availability. Confirm idempotency before
replay because outbox delivery is at least once.

### ParseFailureRateHigh

Compare parser-version rollout timing, file-type mix, malware scan status, and
resource limits. Sample only approved redacted evidence.

### LlmFailureRateHigh

Check the fixed safe failure class, provider health, timeouts, and allowlist.
Do not print prompts, resumes, provider keys, or raw provider responses.

### HostStorageLowWarning / HostStorageLowCritical

Identify the affected filesystem and largest bounded service volume. Stop
growth or add capacity before deleting evidence. Never delete backups or audit
artifacts as an unreviewed first response.

### PostgresConnectionsHighWarning / PostgresConnectionsHighCritical

Inspect connection sources, pool saturation, and long transactions. Prefer
traffic reduction or rollback over increasing `max_connections` without a
memory and recovery assessment.

### MinioMetricsUnavailable

Check the private MinIO endpoint and metrics policy. Do not publish the MinIO
metrics endpoint or use root credentials for scraping.

### BackupStaleWarning / BackupStaleCritical

Confirm the Phase 6C evidence collector is running and distinguish collection
failure from backup failure. For a real stale backup, run the documented backup
workflow and verify a restorable artifact; file existence alone is insufficient.
