# Phase 5 Reports And Export API Report

## Status

`DONE_WITH_CONCERNS`

Implemented the scoped reports/export API, persistent export/audit records, safe CSV generation, private one-time download flow, and PostgreSQL migration/tests.

## Changed Files

- `server/app/reports/api.py`: report, export status, ticket, and controlled download endpoints.
- `server/app/reports/service.py`: job-scoped aggregates, export persistence, CSV generation, authorization re-checks, and ticket lifecycle.
- `server/app/reports/models.py`: persistent export and export-download-ticket models.
- `server/app/reports/schemas.py`: explicit snake_case request/response contracts without storage or secret fields.
- `server/app/reports/csv_export.py`: UTF-8 CSV rendering and formula-prefix neutralization.
- `server/app/reports/storage.py`: private MinIO write/read adapter with bounded downloads.
- `server/app/reports/__init__.py`: reports package boundary.
- `server/app/main.py`: reports router and export-storage wiring only; concurrent talent wiring was preserved and excluded from the implementation commit.
- `server/migrations/versions/0015_reports_exports.py`: reversible export persistence migration.
- `server/tests/test_reports_api.py`: SQLite API, authorization, metric, audit, CSV, idempotency, and download tests.
- `server/tests/test_reports_api_postgres.py`: PostgreSQL tenant/job-scope and concurrent idempotency test.
- `server/tests/test_reports_migration.py`: PostgreSQL upgrade/downgrade/upgrade test.

## API And Data Behavior

- Added `GET /api/v1/reports/recruiting-funnel` with `job_id`, `from`, and `to` filters, current stage counts, stage-event-derived average time, and authorized interview/feedback metrics.
- Added `GET /api/v1/reports/screening-quality` with separate parser success, rule pass, and LLM success numerators/denominators/rates, including zero-denominator behavior.
- Added idempotent `POST /api/v1/exports`, `GET /api/v1/exports/{export_id}`, one-time ticket issuance, and controlled CSV streaming.
- Export creation persists both a `background_jobs` row and an auditable `report_exports` row. Export row selection re-checks the requester's current job authorization.
- CSV output includes application/job/candidate opaque IDs, candidate display name, stage, source, and creation time. It excludes contacts and resume text.
- Every cell beginning with `=`, `+`, `-`, `@`, tab, or carriage return is prefixed with a single quote.
- Export API responses never expose object keys or permanent URLs. Audit metadata contains only export ID and job count for creation, and export ID for download.

## Authorization And Security

- Recruiting admins, recruiters, and hiring managers can read only their effective job scope.
- Hiring managers cannot export under the existing `BULK_EXPORT` policy boundary.
- Interviewers and system admins receive the same non-disclosing `404 resource_not_found` response for existing and nonexistent resources.
- Aggregate queries, export row queries, export-ID reads, ticket issuance, and download all apply organization/user/job scope before returning data.
- Export tickets are caller-bound, expire after 60 seconds, are stored only as SHA-256 hashes, and are single-use.

## Migration

- `0015_reports_exports`, down revision `0014_talent_pools`.
- Adds `report_exports` and `report_export_download_tickets`, tenant-scoped foreign keys, status/invariant checks, and requester/expiry indexes.
- Downgrade removes both tables. PostgreSQL upgrade -> downgrade to `0014_talent_pools` -> upgrade was verified.

## TDD And Verification

- RED: `docker run --rm ux09-server-test python -m pytest server/tests/test_reports_api.py -q` -> 12 failed because the reports package and six API routes did not exist. The initial host-Python attempt was discarded because Python 3.14 lacked server dependencies.
- Focused SQLite GREEN: 12 passed, then 13 passed after adding the hiring-manager boundary test.
- PostgreSQL integration: `test_reports_api_postgres.py` -> 1 passed, proving tenant/job filtering and two-thread idempotent export creation.
- Final focused gate: reports API + PostgreSQL + migration -> 15 passed in 26.10s.
- Main/auth/OpenAPI compatibility gate: 37 passed, 25 deselected in 23.56s.
- `python -m compileall -q server/app server/tests server/migrations/versions` in the Python 3.12 test image -> exit 0.
- `git diff --cached --check` before the implementation commit -> exit 0.
- A broader combined recruiting/interview run exceeded the 120-second command limit and produced no usable result; it is not reported as passing.

## Commits

- `57800a9` - `feat(server): add scoped recruiting reports and exports`

## Unresolved Concerns

- The assigned API slice creates the durable `reports.export` job and implements/test-drives `generate_export`, but the current shared worker handler map does not yet register `reports.export`. The worker owner must register this handler before queued exports complete automatically in a deployed runtime.
- Migration `0015_reports_exports` intentionally follows the concurrent, currently uncommitted `0014_talent_pools` migration already present in the shared worktree. Integration requires that Phase 5 talent migration to land first.
