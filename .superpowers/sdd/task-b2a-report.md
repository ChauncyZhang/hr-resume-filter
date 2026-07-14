# Task B2A Report

## Status

DONE

## Commits

- `d85cdaa` - `feat(governance): add deletion request admission APIs`
- The report is committed separately immediately after this file is written.

## Files changed

- `server/app/governance/api.py`
- `server/app/governance/schemas.py`
- `server/app/governance/authorization.py`
- `server/app/governance/deletion_service.py`
- `server/app/governance/audit.py`
- `server/app/queue/payloads.py`
- `server/app/queue/repository.py`
- `server/tests/test_governance_deletion_api.py`
- `server/tests/test_governance_deletion_postgres.py`
- `.superpowers/sdd/task-b2a-report.md`

The pre-existing user modifications in `.superpowers/sdd/task-1-report.md`,
`.superpowers/sdd/task-2-report.md`, and `app/sample/candidates.csv` were left
untouched and unstaged.

## API and data behavior

- Added authenticated deletion-request create/list/read, approval transition,
  legal-hold placement/release, and candidate governance-status endpoints.
- Reused the existing resource/problem envelopes, generic problem details,
  trace IDs, ETags, signed cursor codec, 24-hour persisted idempotency records,
  and governance no-store behavior.
- Enforced requester/current candidate scope, system-admin-only approval,
  recruiting-admin-only hold management, non-enumerating denials, self-approval
  rejection, current `If-Match`, active-application and active-hold guards, and
  completed-request rejection.
- Built the private manifest exclusively from server-side relational facts and
  projected only the B1 safe manifest fields and exact nine count keys.
- Approval refreshes a stale manifest as a versioned 409 without queueing.
  Failed retry refreshes facts and enqueues one new versioned job only after all
  guards pass.
- Registered strict `governance.delete_candidate` payload validation and terminal
  callback admission. Approval inserts the job in the request transaction with
  dedupe key `candidate-delete:{request_id}:{version}`.
- Legal-hold placement leaves requested deletion unchanged, fails approved
  deletion and cancels its active job atomically, and rejects executing deletion.
- No Worker handler, object deletion, privileged redaction, recovery endpoint,
  retention scheduler, ordinary-read tombstone filtering, or frontend behavior
  was added.

## Security and migration notes

- Every writer locks Candidate first, then deletion request/legal-hold rows, then
  queue/idempotency rows. The idempotency advisory lock is acquired only after
  candidate/domain locks.
- Candidate UUIDs, private row IDs, object keys, names, contacts, resume text,
  filenames, feedback text, URLs, credentials, hold reasons, idempotency keys,
  and manifest hashes are excluded from public deletion resources and audit
  metadata.
- Audit metadata uses explicit allowlists and safe scalar versions/error codes.
  Success mutations and their audit/idempotency/job rows share one transaction;
  rollback tests cover audit and queue failures.
- No schema migration was required; Task B1 revision `0017_governance_deletion`
  already owns the persistence model.

## RED evidence

- Initial focused API/OpenAPI/queue gate:
  `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py -q -x`
  - RED: the first OpenAPI assertion failed because all seven B2A routes and the
    queue registration were absent.
- First full PostgreSQL backend gate:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q`
  - RED: `629 passed, 5 skipped, 7 failed`; all failures were later governance
    migration tests refusing the protected `0017` downgrade because the new
    PostgreSQL fixture left deletion evidence behind.

## GREEN and gate evidence

- Final focused API/PostgreSQL/queue/audit/OpenAPI gate:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py server/tests/test_governance_deletion_postgres.py server/tests/test_governance_api.py server/tests/test_governance_audit.py server/tests/test_queue.py server/tests/test_queue_postgres.py server/tests/test_queue_review.py -q`
  - `90 passed in 119.99s`.
- Fixture-isolation regression plus previously failing migration gate:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_postgres.py server/tests/test_governance_migration.py -q -x`
  - `11 passed in 106.13s`.
- Final full backend suite with PostgreSQL enabled:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q`
  - `636 passed, 5 skipped in 1095.96s`.
- Python 3.12 compile:
  `python -m compileall -q` over changed governance/queue modules and B2A tests
  inside `ux09-server-test` - passed.
- Compose configuration:
  `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet`
  - passed.
- Scoped and staged `git diff --check` - passed.

## Self-review

- Fixed PostgreSQL idempotency operation names that initially embedded resource
  UUIDs and exceeded the existing 64-character column; stable operation names
  now bind resource IDs in the request fingerprint.
- Added post-candidate advisory locking for cross-candidate reuse of the same
  idempotency key without violating candidate-first lock order.
- Added explicit request/hold row locks before idempotency admission for create
  and hold flows.
- Anchored backup-window manifest time to `requested_at`, preventing ordinary
  clock movement from causing false stale-manifest conflicts.
- Ensured failed retry does not mutate its manifest when an approval guard fails.
- Corrected problem/success replay content types and PostgreSQL fixture teardown.
- Confirmed the staged implementation commit contains only brief-owned backend
  files and tests.

## Concerns

- The five full-suite skips are the repository's optional external ClamAV/MinIO
  integration tests; those services were not configured for this gate and are
  outside B2A.
- Queue execution, storage deletion, redaction, recovery, and tombstone filtering
  intentionally remain unimplemented for B2B/B3.

## B2A re-review fixes

The earlier report is corrected as follows: B2A never materializes
`deletion_artifacts`. Artifact locator/checkpoint creation belongs to B2B. A B2A
stale-manifest refresh only removes request-owned artifacts that are still
`pending` with zero attempts, and fails closed if any artifact has started or
been checkpointed.

- Bound deletion-create idempotency fingerprints to `candidate_id`; sequential
  and simultaneous same-key/different-candidate tests now produce exactly one
  201 and one `idempotency_conflict`, never a cross-candidate replay.
- Removed eager artifact materialization from request creation and approval.
  Removed-resume stale refresh coverage proves obsolete unstarted artifacts are
  deleted and no artifact is recreated.
- Added authenticated route-validation and precondition auditing, exact
  event/outcome/safe-code assertions, generic `governance.request_rejected`, and
  fail-closed 503 `audit_unavailable` behavior when required rejection/read audit
  persistence fails. Unauthenticated validation does not audit body values or IDs.
- Approval now locks active legal-hold rows before idempotency admission, keeping
  Candidate -> request/hold -> queue/idempotency ordering.
- Added a real two-tenant matrix across all seven B2A endpoints and all relevant
  roles, asserting known foreign IDs remain non-enumerating and mutation-free.
- Added bounded barriers and joins to every B2A threaded PostgreSQL test; the
  approve-vs-hold race rejects exceptions/500s and accepts only serialized end
  states with no executable delete job under an active hold.
- Seeded unique candidate, contact, resume, file/storage, application, interview,
  URL, credential, and feedback values and recursively checked every nested
  success, problem, and audit response value for their absence.
- Requester cursors now bind `principal.user_id`; another same-tenant requester
  cannot reuse the token. Requester list rows use the same current candidate-read
  predicate as individual reads, without hardcoded requester role labels.

### Re-review RED evidence

- `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py -q -x`
  - RED: `1 failed, 8 passed`; `test_create_idempotency_key_is_bound_to_candidate`
    received 201 for the second candidate instead of 409
    `idempotency_conflict`, proving the false cross-candidate replay.
- `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py::test_authenticated_list_denial_is_audited -q`
  - RED: `1 failed`; the authenticated inactive-principal list denial returned
    404 with no `governance.deletion_requests_listed` audit row.

### Re-review GREEN evidence

- Focused API gate:
  `docker run --rm -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py -q -x`
  - `21 passed in 26.92s`.
- PostgreSQL barriers:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_postgres.py -q -x`
  - `5 passed in 26.85s`.
- Final focused API/PostgreSQL/queue/audit/OpenAPI gate:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py server/tests/test_governance_deletion_postgres.py server/tests/test_governance_api.py server/tests/test_governance_audit.py server/tests/test_queue.py server/tests/test_queue_postgres.py server/tests/test_queue_review.py -q`
  - `96 passed in 102.52s`.
- Final full backend PostgreSQL suite:
  `docker run --rm -e POSTGRES_SMOKE_URL=... -v "${PWD}:/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests -q`
  - `642 passed, 5 skipped in 939.99s`.
- Python 3.12 compile over changed governance/queue modules and B2A tests:
  passed.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet`:
  passed.
- Scoped and staged `git diff --check`: passed.

The five skips remain the optional external ClamAV/MinIO tests. No B2B Worker,
storage, redaction, recovery, tombstone-filtering, frontend, migration, or deploy
behavior was added.
