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

Store `QUEUE_METRICS_DB_USER` / `QUEUE_METRICS_DB_PASSWORD` and
`POSTGRES_EXPORTER_DB_USER` / `POSTGRES_EXPORTER_DB_PASSWORD` as two distinct
credential pairs in the deployment secret environment. The queue identity can
read only `observability.queue_metrics`; the postgres-exporter identity has
`pg_monitor` and no queue view or table access. Never substitute application or
database-owner credentials into either exporter DSN.

Run the formal preflight from the repository root. It first runs the production
preflight (including the Docker Compose version gate), then validates the fixed
base + production + observability model:

```sh
COMPOSE_ENV_FILE=deploy/.env sh deploy/observability-preflight.sh
```

After it passes, start the fixed three-file model. The one-shot
`observability-role-provision` service idempotently creates the two logins and
safe aggregate view before either database exporter starts:

```sh
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml up -d
```

Confirm the proxy is the only service with a published port. Start
Alertmanager, exporters, and Prometheus first. Confirm every private
   target is up, then roll one API instance with the metrics-enabled image.
Exercise live, ready, one template route, and a disposable queue item.
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

### ApiHigh5xxRateWarning

Check the failing template routes, readiness results, and the most recent API
deployment. Roll back progressively if failures began with a release. Do not
log request bodies or headers while investigating.

### ApiHigh5xxRateCritical

Use the warning procedure immediately and treat sustained user-facing errors as
an incident requiring traffic reduction or rollback.

### ApiHighLatencyWarning

Compare route-template latency with database connections, host CPU, and
storage readiness. Reduce traffic or roll back before raising capacity limits.

### ApiHighLatencyCritical

Use the warning procedure immediately and reduce load or roll back while the
latency objective is materially breached.

### ApiReadinessFailure

Identify the fixed `dependency` label, then check PostgreSQL or MinIO health
from the private network. Liveness remaining green does not make the instance
safe to receive traffic.

### QueueCollectorDown

Check the exporter target, read-only role connectivity, and schema grants.
Never replace the monitoring DSN with owner or application credentials.

### QueueOldestReadyTooOldWarning

Check worker liveness, lease churn, job-type backlog, and downstream capacity.
Scale workers gradually only after verifying the dependency can absorb load.

### QueueOldestReadyTooOldCritical

Use the warning procedure, stop nonessential producers if safe, and restore
worker/dependency capacity before attempting replay.

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

### HostStorageLowWarning

Identify the affected filesystem and largest bounded service volume. Stop
growth or add capacity before deleting evidence. Never delete backups or audit
artifacts as an unreviewed first response.

### HostStorageLowCritical

Use the warning procedure immediately. Protect database and object-store write
paths while adding capacity or safely reducing retained non-evidence data.

### PostgresConnectionsHighWarning

Inspect connection sources, pool saturation, and long transactions. Prefer
traffic reduction or rollback over increasing `max_connections` without a
memory and recovery assessment.

### PostgresConnectionsHighCritical

Use the warning procedure immediately and shed load or roll back before the
database exhausts connection slots.

### MinioMetricsUnavailable

Check the private MinIO endpoint and metrics policy. Do not publish the MinIO
metrics endpoint or use root credentials for scraping.

## Deferred integrations

Backup freshness alerts are disabled until Phase 6C supplies and validates the
backup evidence collector. Missing backup metrics must not page as critical.
Phase 6C must add restore-aware evidence semantics, alert tests, and an operator
procedure before enabling this signal.

Container-level metrics are also deferred. The default overlay intentionally
does not run cAdvisor or mount the Docker socket, `/var/run`, Docker storage, or
the host root filesystem. Initial capacity coverage comes from node-exporter,
postgres-exporter, and MinIO metrics. Revisit container metrics only with a
reviewed design that requires neither a container-engine socket nor privileged
host mounts.
