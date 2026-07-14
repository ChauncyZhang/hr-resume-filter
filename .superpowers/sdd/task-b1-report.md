# Task B1 Report

## Status

DONE

## Commits

- `52df461` — `feat(governance): add deletion foundation`
- `b10e37b` — `docs(governance): report task B1 verification`
- `0228262` — `fix(governance): harden deletion foundation`
- `623ec8c` — `docs(governance): record task B1 review fixes`
- `ea543a4` — `test(governance): stabilize audit clock fixture`

## Files changed

- `server/app/governance/deletion_models.py`
- `server/app/governance/deletion_service.py`
- `server/migrations/versions/0017_governance_deletion.py`
- `server/tests/test_governance_deletion_models.py`
- `server/tests/test_governance_deletion_migration.py`
- `server/tests/test_deploy_database_identity.py`
- `server/tests/test_governance_api.py`
- `server/app/governance/__init__.py`
- `server/app/recruiting/models.py`
- `deploy/compose.yaml`
- `deploy/.env.example`
- `deploy/postgres/provision-app-role.sh`
- `server/Dockerfile`
- `server/README.md`
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

## Review-fix RED evidence

- `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_deploy_database_identity.py -q`
  - RED: `6 failed, 30 passed in 6.69s`; failures proved count coercion/overflow, length-only ORM hash validation, and API/worker use of bootstrap database credentials.
- `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_migration.py -q -k 'dynamically or lowercase_hex or downgrade_waits'`
  - After correcting a test-only multi-statement psycopg setup error, RED was `5 failed, 2 passed, 9 deselected in 142.42s`; uppercase/non-hex hashes were accepted and downgrade never waited for an audit-table lock.
- `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_deploy_database_identity.py -q -k shared_owner`
  - RED: `2 failed, 3 deselected in 0.98s`; the role script reached `psql` instead of rejecting shared owner/app identities and passwords.

## Review-fix GREEN and gate evidence

- Pure model/domain plus Compose contract:
  - `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_deploy_database_identity.py -q`
  - `36 passed in 4.02s` before the final distinct-credential guard; the final deploy-only gate was `5 passed in 1.72s`.
- Provision script idempotency:
  - Copied `deploy/postgres/provision-app-role.sh` into isolated PostgreSQL 16.9 container `ux09-b1-review-pg` and ran it twice with distinct test-only owner/app credentials.
  - Both runs exited `0`.
- Complete focused PostgreSQL gate:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -e APP_DB_TEST_USER=ux09_app -e APP_DB_TEST_PASSWORD=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_deploy_database_identity.py server/tests/test_governance_deletion_migration.py -q --durations=10`
  - `48 passed in 298.59s`.
- Final role/pure regression gate after the credential guard:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -e APP_DB_TEST_USER=ux09_app -e APP_DB_TEST_PASSWORD=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_models.py server/tests/test_deploy_database_identity.py server/tests/test_governance_deletion_migration.py::test_provisioned_application_role_is_unprivileged_and_cannot_mutate_evidence -q`
  - `39 passed in 15.53s`.
- Full backend PostgreSQL suite:
  - `docker run --rm -e POSTGRES_SMOKE_URL=... -e APP_DB_TEST_USER=ux09_app -e APP_DB_TEST_PASSWORD=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q --durations=20`
  - The run recorded one failure by 11% and was stopped after remaining CPU-bound progress stalled at 81% beyond 25 minutes.
  - Diagnostic rerun: `docker run --rm -e POSTGRES_SMOKE_URL=... -e APP_DB_TEST_USER=ux09_app -e APP_DB_TEST_PASSWORD=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -x -vv`
  - `1 failed, 10 passed, 1 skipped in 25.38s`: pre-existing `server/tests/test_governance_api.py::test_real_candidate_writer_is_recruiting_visible_for_role_union_only` expected `candidate.created` but received an empty recruiter audit list. The same test failed alone (`1 failed in 9.84s`) and no Task B1 review-fix file changes that API path.
  - Root cause: that test fixed the governance query clock at `2026-07-14T12:00:00Z` while real audit writers used wall-clock time. Runs after that fixed instant excluded newly written audit rows as future data.
  - Stabilization gate after normalizing only that test's produced audit timestamps to its fixed clock: `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_api.py -q` — `13 passed in 27.86s`.
  - Final clean rerun against a fresh PostgreSQL 16.9 database with distinct migration-owner and application identities: `docker run --rm --name ux09-b1-final-suite -e POSTGRES_SMOKE_URL=... -e APP_DB_TEST_USER=ux09_app -e APP_DB_TEST_PASSWORD=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q` — `617 passed, 4 skipped in 1374.14s`.
- Compile, Compose, shell, and diff checks:
  - `docker build --target test -t ux09-server-test -f server/Dockerfile .` — passed.
  - `docker run --rm ... ux09-server-test python -m compileall -q <changed Python files>` — passed.
  - `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 postgres:16.9-alpine sh -n deploy/postgres/provision-app-role.sh` — passed.
  - `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet` — passed.
  - Scoped `git diff --check` and staged `git diff --cached --check` — passed.

## Review-fix behavior and residual boundary

- API/worker Compose URLs now use a dedicated LOGIN app role. PostgreSQL bootstrap/migrations retain the owner role; Alembic creates no roles or passwords. The idempotent operator script reconciles least-privilege table/sequence grants, excludes audit UPDATE/DELETE and function grants, and rejects shared owner/app credentials.
- Downgrade takes deterministic `ACCESS EXCLUSIVE` locks on `audit_logs`, `candidates`, and all four Task B tables before checking evidence. The coordinated writer test proves downgrade waits, observes the committed evidence, refuses, and leaves all additive objects intact.
- Tests now generate the full 25-edge state matrix and dynamically discover/assert all eight required composite tenant FK families. Manifest counts require exact bounded integers, and manifest hashes require exactly 64 lowercase hexadecimal characters in ORM and PostgreSQL constraints.
- Independent re-review approved Task B1 specification compliance with no Critical or Important findings. The final full backend suite is clean; the four skips remain the explicitly optional ClamAV/MinIO smoke integrations. The privileged redaction body remains deliberately fail-closed and belongs to B2.
