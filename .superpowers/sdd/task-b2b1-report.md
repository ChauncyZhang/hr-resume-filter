# Task B2B1 report

## Status and commits

- Status: complete; all eight security-review findings are closed with focused regression and live PostgreSQL/MinIO evidence.
- Implementation commit: `662c919 feat(governance): add secure deletion execution foundation`.
- This report is committed separately after the implementation commit.
- Scope remained B2B1-only. No deletion/retention/recovery handler registration, request transitions, recovery CLI, frontend work, B2B2, or B2B3 behavior was added.

## Delivered behavior

- Added a dedicated, least-privilege PostgreSQL governance login and executor role. Provisioning converges legacy role memberships, rejects shared identities/passwords, and grants only execution of the redaction routine.
- Completed the `0017` `SECURITY DEFINER` redaction routine with fixed search path, request/organization/candidate/state checks, candidate-version binding, deterministic tombstone retry, full PII cleanup, narrow audit de-linking, and a timezone-independent checksum/fact tuple.
- Added canonical signed-ledger v1 validation and HMAC verification. Writes use conditional create and fail closed on unsupported clients, malformed/tampered existing data, or concurrent mismatch.
- Added a delete-only storage adapter and real MinIO users/policies for ordinary app, deletion, and ledger identities. Provisioning is repeatable, supports credential rotation, revokes retired users, and aligns report deletion with the real `resumes/exports/` storage path.
- Added production settings validation for missing/shared/placeholder credentials and a high-entropy ledger signing key without exposing secret values.
- Bounded PostgreSQL migration subprocesses to 60 seconds so a genuine migration stall fails with a diagnostic timeout.

## Test-first evidence

All credential values used below were disposable local values supplied through environment variables and are intentionally omitted from this report.

### RED

- Baseline image: `docker run --rm ux09-b2b1-baseline` -> `543 passed, 100 skipped, 4 failed`; failures proved the test image did not contain the complete deploy contract. The Dockerfile was changed to copy `deploy/` into the test image.
- Initial settings/deploy/MinIO gate -> `19 failed, 32 passed, 1 skipped`, proving missing governance credential validation, topology separation, policy provisioning, and ledger/storage behavior.
- Initial live PostgreSQL gate -> undefined `redact_candidate_data`, then focused contract expansion produced `5 failed, 6 passed`, proving the candidate-version, retry cleanup, PII inventory, audit, and privilege gaps.
- Fingerprint/state, timezone, and unconditional-ledger-write regressions -> MinIO `1 failed, 6 passed, 1 skipped`; PostgreSQL `2 failed, 6 passed`.
- Eight-finding review RED: settings/deploy `7 failed, 46 passed`; PostgreSQL `5 failed, 6 passed`; tombstone partial restore raised `redaction_tombstone_invalid`; retired-key collision and repeated rotation provisioning each failed before their fixes.
- Exact MinIO repeatability reproduction: a second provisioning run with an already-removed retired user failed with `specified user does not exist`; the minimal fix checks user existence before removal.

### GREEN focused and live gates

- `python -m pytest server/tests/test_governance_deletion_migration.py server/tests/test_governance_redaction_postgres.py -q` against real PostgreSQL roles -> `23 passed in 120.89s` on the final rebuilt test image. An earlier equivalent run was `23 passed in 172.55s`.
- `python -m pytest server/tests/test_settings.py server/tests/test_deploy_database_identity.py -q` -> `56 passed`.
- Real MinIO denial smoke after restoring the normal identities: `python -m pytest server/tests/test_governance_minio.py -q` -> `8 passed, 1 skipped in 1.34s`; the only skip is the separately configured rotation case.
- Real MinIO rotation smoke with separate current/retired credentials -> `9 passed in 0.84s`; old delete/ledger keys were denied, new identities worked, and both rotation and restoration provisioning succeeded twice.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet` with disposable required environment -> passed.
- `sh -n deploy/postgres/provision-app-role.sh` and `sh -n deploy/minio/provision.sh` -> passed.
- `python -m compileall -q server/app server/migrations` in the rebuilt test image -> passed.
- Host `python -m pytest server/tests/test_production_topology.py -q` with the concurrent Phase6B-required observability environment -> `9 passed in 5.08s`.
- Container backend full suite, excluding only the Docker-CLI-dependent topology file as agreed -> `689 passed, 2 skipped in 1003.62s`, exit 0. The host topology gate covers the excluded file.
- Staged `git diff --cached --check` -> passed.
- Staged private-key/provider-token pattern scan and governance log-sink scan -> passed.

## Full-suite CPU investigation

- SIGINT captured the apparent stall at `test_llm_postgres.py::test_llm_tables_are_tenant_scoped_and_evidence_is_append_only`, with pytest waiting for an Alembic subprocess.
- The target alone passed in `4.85s`; interview predecessor plus target passed `4` tests in `31.24s`; migration predecessor plus target passed `13` tests in `163s`; the exact 259-test predecessor sequence plus target completed `259 passed, 1 skipped in 509.6s`.
- The interrupted pytest process had only `562.40s` elapsed and about `2:20` CPU despite the container being up for more than four hours. No reproducible sequence dependency or CPU loop existed; the long wall time was an external pause. A 60-second Alembic subprocess timeout was retained as the bounded regression guard.
- A later full run crossed the same location and completed. Three observed `production_topology` failures were solely `FileNotFoundError: docker` inside the test container and were handled by the agreed host/container split, not treated as B2B1 failures.

## Eight security findings

1. Role graph convergence: closed. Provisioning removes stale inbound/outbound governance memberships; real PostgreSQL tests prove app/owner/arbitrary roles cannot inherit or execute the routine and the governance role cannot perform unrelated DML.
2. Approved manifest candidate-version binding: closed. First redaction rejects post-approval candidate mutation with safe `redaction_manifest_stale` and zero mutation.
3. Tombstone retry cleanup: closed. Every invocation re-discovers and re-cleans linked PII; restored tombstone data is removed without changing `deleted_at`, version, or checksum.
4. PII inventory: closed. Added `applications.source`, `interviews.round_name`, deterministic non-linkable `llm_invocations.input_sha256`, and deletion of candidate-linked idempotency rows while retaining unrelated tenant/request rows.
5. Audit de-linking: closed. Candidate/resume/file/application/screening/interview/feedback resource IDs and only allowlisted metadata keys are removed; the trigger rejects broader mutations.
6. Report object path: closed. Delete policy and live smoke use the service's actual `resumes/exports/...` contract and deny unrelated prefixes/read/write access.
7. MinIO identity reuse/rotation: closed. Pairwise key/secret reuse and retired-key conflicts fail closed; real two-way rotation proves retired keys fail and repeated policy/user provisioning succeeds.
8. Signing-key strength: closed. Production requires at least 32 UTF-8 bytes, no whitespace/placeholders, and minimum character diversity; boundary tests cover rejection and valid behavior.

## Files

- Deploy/config: `deploy/.env.example`, `deploy/compose.yaml`, `deploy/minio/provision.sh`, `deploy/postgres/provision-app-role.sh`, `server/Dockerfile`, `server/README.md`.
- Runtime: `server/app/core/settings.py`, `server/app/governance/deletion_service.py`, `server/app/governance/storage.py`.
- Migration: `server/migrations/versions/0017_governance_deletion.py`.
- Tests: `server/tests/test_deploy_database_identity.py`, `server/tests/test_governance_deletion_migration.py`, `server/tests/test_governance_minio.py`, `server/tests/test_governance_redaction_postgres.py`, `server/tests/test_settings.py`.

## Self-review and concerns

- Staging was checked against an explicit 15-file B2B1 allowlist. The three protected user files and all concurrent Phase6B WIP files were neither staged nor changed by this task.
- API runtime does not receive governance DB/delete/ledger/signing credentials; the worker retains ordinary credentials for normal work and receives only the dedicated governance settings.
- Errors and checksums contain no names, object keys, row identifiers, secret values, or source PII. Ledger fields are strict and recursively tested against the forbidden-field inventory.
- The migration is an unreleased revision, and downgrade remains fail-closed when governance evidence exists.
- No unresolved B2B1 code or security concern remains. The two full-suite skips are covered by separately executed live gates where applicable. Concurrent Phase6B WIP was explicitly excluded from B2B1 staging and evidence attribution.
