# Phase 6B review remediation report

## Status

All independent-review findings are remediated within the Phase 6B write set.
The production topology still publishes only the HTTPS proxy port; API and
exporter metrics remain private, and public `/metrics` paths still return 404.
No B2B governance/migration file, shared Dockerfile/README/settings file, or
user-owned file was modified or staged by this remediation.

## Finding-by-finding remediation

1. **Disposable PostgreSQL safety.** Every real-PG test checks
   `DISPOSABLE_DATABASE_CONFIRMED=1` before connecting and then executes only
   `SELECT current_database()` until the database is proven to be exactly
   `ux09_observability_test`. Focused tests prove a missing flag makes no
   connection and a wrong database executes zero DDL/DML.
2. **Backup freshness.** `BackupStaleWarning` and `BackupStaleCritical` are
   removed. Backup freshness remains disabled until Phase 6C provides a tested,
   restore-aware evidence collector; missing metrics cannot page as critical.
3. **Readiness results and dependency identity.** The alert now uses
   `sum by (dependency)` over `result=~"failed|cancelled"`. A real promtool rule
   test triggers and resolves a cancelled storage check while retaining the
   `dependency="storage"` alert label. Timed-out probes are recorded as
   cancelled by the existing readiness instrumentation.
4. **Safe capacity topology.** cAdvisor and its privileged/Docker/host mounts
   are removed from both Compose and Prometheus. Tests reject `privileged`,
   `/var/run`, Docker sockets/storage, and host-root mounts. Initial capacity
   signals are node-exporter, postgres-exporter, and private MinIO metrics.
5. **Resolvable runbooks.** All 18 alert `runbook_url` values are absolute
   canonical GitHub HTTPS links. Each fragment maps to a dedicated Markdown
   heading and is checked against the generated anchor set.
6. **Least-privilege monitoring identities.** The idempotent
   `deploy/observability/provision-roles.sh` creates two distinct logins. The
   queue exporter receives only `USAGE` on `observability` and `SELECT` on the
   bounded aggregate view `observability.queue_metrics`; it has no queue base
   table access and no `pg_monitor`. The third-party postgres-exporter receives
   `pg_monitor`, no queue view/table access, and a separate DSN/password. The
   collector now issues one query against the safe view and never queries queue
   base tables.
7. **Formal three-layer preflight.** `deploy/observability-preflight.sh` first
   calls `production-preflight.sh`, inheriting its Docker Compose >= 2.24.4
   check, then validates the fixed base + production + observability model.
   The runbook contains copyable preflight and launch commands.
8. **Review evidence.** This report records RED/GREEN evidence, deferred
   integrations, and the intended commit subject.

## TDD evidence

The focused RED run failed on the intended old contracts: missing disposable
database guard, direct queue-table collector SQL, absent role/preflight scripts,
cAdvisor and host mounts still present, backup alerts still enabled, relative
runbook URLs, and readiness aggregation that lost `dependency`. Host Docker
cases were rerun on the host after the container-only RED environment correctly
reported that it lacked a Docker CLI.

Final GREEN evidence:

- Disposable real PostgreSQL exporter and role/grant suite: `8 passed`.
- Affected HTTP, runtime, exporter, privacy, and role unit tests: `19 passed,
  2 deselected` (the real-PG cases were run separately above).
- Phase 6A + Phase 6B host topology suite: `14 passed`.
- Formal preflight test: `1 passed`; installed preflight and direct three-file
  `docker compose ... config --quiet` both exited zero.
- Real promtool configuration/rule load: 18 rules; real amtool configuration
  load: success. Representative promtool trigger/resolution tests passed.
- POSIX `sh -n` for both new scripts: success.
- Runtime image build: success. A real runtime exporter using the restricted
  queue login returned `ux09_queue_collector_up 1.0` and bounded lease metrics.
- Python compile, production PII canary scan, `git diff --check`, and
  owned-only staged-diff audit are final commit gates.

## Deferred integrations and concerns

- Phase 6C owns backup evidence semantics, freshness metrics, restore-aware
  tests, and backup alert enablement.
- Container-level metrics remain deferred until a reviewed design requires
  neither a container-engine socket nor privileged host mounts.
- The four exporter identity/password values must be supplied by the approved
  deployment secret mechanism; the B2B-owned `.env.example` is intentionally
  unchanged.
- MinIO's metrics endpoint is public only inside the private Compose network.
  A dedicated authenticated MinIO metrics identity remains a future hardening
  option if supported by the deployed MinIO contract.
- Alertmanager still uses the null canary receiver; production routing and
  credentials require the approved external secret integration.

## Commit

Intended subject: `fix(observability): close Phase6B review findings`.
The immutable commit hash is reported in the final handoff because a commit
cannot contain its own hash.
