# Task B1 Report

## Status

DONE

## Commits

- `52df461` — `feat(governance): add deletion foundation`
- Report: committed separately after this report was written.

## Files changed

- `server/app/governance/deletion_models.py`
- `server/app/governance/deletion_service.py`
- `server/migrations/versions/0017_governance_deletion.py`
- `server/tests/test_governance_deletion_models.py`
- `server/tests/test_governance_deletion_migration.py`
- `server/app/governance/__init__.py`
- `server/app/recruiting/models.py`
- `.superpowers/sdd/task-b1-report.md`

The pre-existing user modifications in `.superpowers/sdd/task-1-report.md`, `.superpowers/sdd/task-2-report.md`, and `app/sample/candidates.csv` were left unstaged and untouched.

## API and data behavior

- Added nullable `candidates.deleted_at`.
- Added tenant-scoped `deletion_requests`, `deletion_artifacts`, `legal_holds`, and `deletion_recovery_runs` persistence with PostgreSQL checks, composite tenant foreign keys, partial unique indexes, and non-negative/version constraints.
- The deletion-request contract uses `reason_code`, has no `executed_by`, and retains `approved_by`, `approved_at`, `execution_started_at`, and `completed_at`.
- Added pure deletion-domain state transitions, approval guards, legal-hold outcomes, completed-request rejection, recovery-generation validation, canonical private-manifest hashing, and safe v1 impact projection.
- The public projection contains only `schema_version`, request ID as `candidate_ref`, candidate/policy versions, the exact nine required count keys, and `backup_window_ends_at`.
- No HTTP routes, queue handlers, object deletion, recovery CLI behavior, or frontend behavior were added.

## Security and migration notes

- Candidate/request, hold/candidate, actor, artifact/request, and recovery/job relationships use organization-scoped foreign keys.
- The private manifest is PostgreSQL JSONB; storage keys remain private artifact data and are never projected.
- Domain failures expose stable safe codes only. Invalid private manifests suppress underlying value-bearing conversion/serialization errors.
- Manifest hashes use canonical JSON plus SHA-256; approval comparison uses constant-time digest comparison.
- Revision `0017_governance_deletion` follows `0016a_audit_category_repair` and creates no passwords or secret values.
- The privileged audit-redaction function is intentionally a fail-closed stub: `PUBLIC` and the tested application role cannot execute it, while an owner call raises `audit redaction unavailable`. The complete redaction body and audit-trigger allowance remain B2 work.
- Downgrade removes an empty additive schema, but refuses with an operator-facing error when deletion requests/artifacts, legal holds, recovery runs, deletion ledger events, or candidate tombstones exist.

## RED evidence

- `docker run --rm -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py -q`
  - RED: collection failed with `ModuleNotFoundError: No module named 'server.app.governance.deletion_models'`.
- `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_migration.py -q -x`
  - RED: Alembic failed with `Can't locate revision identified by '0017_governance_deletion'`.
- Corrected-contract rerun of `test_governance_deletion_models.py -q -x`
  - RED: `reason_code` was absent from `deletion_requests` before the controller correction was implemented.
- Private-manifest rejection rerun of `test_governance_deletion_models.py -q -x`
  - RED: an invalid private count escaped as a raw value-bearing `ValueError` before safe-code handling was implemented.

An initial host-Python attempt was an environment error because the default Python 3.14 installation lacked SQLAlchemy; all valid RED/GREEN evidence used the repository's documented Python 3.12 Docker test environment.

## GREEN and gate evidence

- Pure domain/model gate:
  - `docker run --rm -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py -q`
  - `32 passed in 1.25s`.
- Final focused PostgreSQL gate:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_governance_deletion_migration.py -q`
  - `40 passed in 98.86s`.
- Focused compatibility gate:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_governance_deletion_migration.py server/tests/test_governance_models.py server/tests/test_governance_audit.py server/tests/test_bootstrap.py -q`
  - `56 passed in 75.41s` before the test-isolation-only cleanup edit; that edit was subsequently covered by the final focused and full-suite gates.
- Full backend suite with PostgreSQL enabled:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${repo}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q`
  - `607 passed, 4 skipped in 860.91s`; the skips were the optional ClamAV smoke test and three optional MinIO smoke tests because those endpoints were not configured.
- Compile:
  - `python -m compileall -q` over all changed Python modules/tests inside the Python 3.12 test image: passed.
- Whitespace:
  - Scoped `git diff --check` and staged `git diff --cached --check`: passed.

## Self-review findings

- Fixed SQLite compatibility by using portable `length(...)` checks in ORM metadata.
- Fixed isolated model registration by registering queue metadata required by the optional recovery job foreign key.
- Fixed migration test isolation so deliberate downgrade-refusal evidence cannot contaminate later migration suites.
- Confirmed exact corrected contract names: `reason_code`, `backup_window_ends_at`, nine fixed count keys, and no deletion-request `executed_by`.
- Confirmed only brief-owned implementation/compatibility files and this required report were changed.

## Remaining concerns

- The privileged redaction function deliberately remains fail-closed until B2; no redaction or audit-trigger exception path exists in this task.
- External ClamAV and MinIO smoke integrations were not configured, accounting for all four full-suite skips; they are unrelated to the Task B1 database/domain surface.
