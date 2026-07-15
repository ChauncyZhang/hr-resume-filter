# Phase 6B implementation report

## Status

Implemented the Phase 6B first-release HTTP, generic queue, and capacity
observability surfaces within the assigned write set. Production remains a
single-public-port topology: only the HTTPS proxy publishes a host port, the
proxy still returns 404 for `/metrics` and every child path, and Prometheus can
scrape the API on the private Compose network.

Deployment is conditionally ready. The application image and independent queue
exporter entrypoint run successfully, but production rollout must wait for the
shared PostgreSQL provisioning work to create and grant the dedicated read-only
monitoring identity described in the runbook.

## Owned files

Created:

- `server/app/observability/__init__.py`
- `server/app/observability/http_metrics.py`
- `server/app/observability/exporter.py`
- `server/app/observability/collectors.py`
- `server/tests/test_http_metrics.py`
- `server/tests/test_observability_exporter.py`
- `server/tests/test_observability_privacy.py`
- `server/tests/test_observability_topology.py`
- `deploy/compose.observability.yaml`
- `deploy/observability/prometheus.yml`
- `deploy/observability/alerts/ux09.rules.yml`
- `deploy/observability/alertmanager.yml`
- `deploy/observability/runbook.md`
- `.superpowers/sdd/task-phase6b-report.md`

Modified:

- `server/app/main.py`
- `server/app/core/logging.py`
- `server/requirements.txt`
- `server/tests/test_observability.py`
- `server/tests/test_production_topology.py`

No Dockerfile, README, settings, base/production Compose, Nginx, Worker, queue,
governance, migration, B2B1-owned, or user-owned file was modified or staged by
this task.

## Behavior and SLI coverage

- The API exposes `/metrics` only on its private service port. HTTP request
  counters and histograms use bounded method, template route, and status-class
  labels. Unknown methods become `OTHER`; unmatched paths become `unmatched`.
- Request logs now use template routes instead of raw paths. Structured
  redaction also covers bodies, headers, payloads, database URLs, and object or
  ledger keys.
- Login failures use fixed safe reasons. Readiness count and duration use only
  the fixed `database` and `storage` dependency values and fixed result values.
- The independent exporter collects persisted job counts, oldest runnable age,
  attempt result/count/duration, expired leases, dead letters, outbox counts,
  and oldest outbox age. Unknown dimensions collapse and aggregate into one
  `other` series; safe error codes collapse into fixed classes.
- All `governance.*` job metrics are suppressed until the governance job and
  terminal contracts freeze.
- Prometheus scrapes API, queue exporter, node-exporter, cAdvisor,
  postgres-exporter, and private MinIO metrics. Prometheus, Alertmanager, and
  exporters publish no host ports.
- Warning and critical alerts cover API 5xx and p95 latency, readiness, queue
  age, expired leases, dead letters, outbox age, parse/LLM failure ratio,
  filesystem capacity below 20%/10%, PostgreSQL connection saturation, MinIO
  metric availability, and backup evidence older than 26/36 hours.
- The runbook defines 30-day API/readiness/queue objectives, progressive
  rollout, rollback, privacy constraints, and symptom-oriented triage.

## TDD evidence

Initial focused RED:

```text
docker exec ux09-phase6b-tests python -m pytest \
  server/tests/test_http_metrics.py \
  server/tests/test_observability_exporter.py \
  server/tests/test_observability_privacy.py \
  server/tests/test_observability.py -q

7 failed, 5 passed
```

The failures were the intended missing behavior: API `/metrics` returned 404,
the observability package did not exist, and request logs contained raw path
identifiers. The host topology RED reported `4 failed` because the third
Compose overlay and Prometheus/Alertmanager files did not exist.

Additional focused RED/GREEN cycles proved that an attacker-controlled HTTP
method must collapse to `OTHER`, multiple unknown database dimensions must
aggregate into one time series, and login failures must use a fixed reason.
Each new test failed against the prior implementation before the minimal fix.

Final focused GREEN with a real disposable PostgreSQL fixture:

```text
20 passed in 8.94s
```

The real database test inserted generic, unknown, and governance rows, then
proved SQL-backed job/outbox metrics, safe error classification, governance
suppression, and PII canary removal.

## Verification evidence

- Focused HTTP/exporter/privacy/existing health and observability tests with
  real PostgreSQL: `20 passed in 8.94s`.
- Observability plus Phase 6A production topology host tests: `14 passed in
  8.02s`. This includes real `promtool`, real `amtool`, disposable TLS/Nginx,
  public `/metrics` and `/metrics/child` 404 checks, and representative alert
  trigger/resolution tests.
- Real private-network smoke: Prometheus, Alertmanager, and API processes all
  remained running; Prometheus reported the private `api:8000/metrics` target
  `up`. None published a host port.
- Runtime image build: `docker build --target runtime ...` exited zero.
- Independent exporter HTTP smoke against disposable PostgreSQL returned
  `ux09_queue_collector_up 1` and generic job/outbox metrics.
- Three-file `docker compose ... config --quiet`: exit zero.
- `compileall` for observability, main, and logging: exit zero.
- Production PII canary scan over application and observability deployment
  files: clean.
- Pinned node-exporter, cAdvisor, and postgres-exporter images pulled and their
  real binaries returned the expected versions.

An attempted backend-wide run excluding host-Docker topology tests exceeded the
240-second local execution limit and was terminated with no final pytest
summary. Focused and affected suites are green; the complete backend suite
remains an integration-gate responsibility.

## Rollout and rollback

Roll out in stages: provision the read-only monitoring identity, validate the
three-file model, start Alertmanager/exporters/Prometheus without notification
delivery, verify private targets, canary one API instance, then enable warning
delivery before critical paging. Do not expose a monitoring host port to repair
a scrape problem.

Rollback is to disable notifications, stop only the observability-overlay
services, and restore the prior API image. Preserve Prometheus data for incident
evidence. The base and production Compose files were not modified by Phase 6B.

## Concerns and integration gaps

- The dedicated `OBSERVABILITY_DB_USER` role and grants are intentionally not
  provisioned here because `deploy/.env.example`, base Compose, and PostgreSQL
  provisioning are B2B1-owned. Production startup will fail closed until that
  integration is completed.
- MinIO metrics use its public-metrics mode only inside the internal Compose
  network. A dedicated authenticated MinIO monitoring identity remains a
  follow-up if the deployed MinIO metric endpoint supports that contract.
- Backup alerts intentionally fire on absent evidence. Phase 6C must publish
  `ux09_backup_last_success_timestamp_seconds` and the planned backup size and
  success metrics before those alerts can represent backup state rather than
  collector absence.
- Alertmanager has a null default receiver so no external payload leaves the
  deployment during canary. Production routing and receiver credentials must be
  supplied through an approved secret mechanism and rechecked with a PII canary.
- cAdvisor requires privileged host visibility. It was image/version checked,
  not started with production host mounts on Docker Desktop; approve and verify
  that permission on the target Linux host before rollout.
- No production CA, DNS, firewall, receiver delivery, retention sizing, or live
  restore validation was performed.

## Commit

The intended commit message is `feat(observability): add private metrics and
capacity monitoring`. The resulting commit hash is reported after this report
is included in the same commit, avoiding a self-referential hash in the commit
contents.
