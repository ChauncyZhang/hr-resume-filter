# Task 2 Report: Identity, Sessions, CSRF, and RBAC

## Result

Implemented the Phase 1 identity boundary in commit `93e2aba`.

## RED / GREEN evidence

- RED: the first Python 3.12 Docker run failed during collection with three
  `ModuleNotFoundError: No module named 'server.app.identity'` errors after the
  identity, policy, and bootstrap tests were added before production code.
- GREEN focused: `23 passed in 6.37s` for identity, policy, and bootstrap tests.
- GREEN full Docker image: `55 passed, 1 skipped in 7.81s`; the skipped test is
  the explicitly environment-gated PostgreSQL migration smoke.
- GREEN PostgreSQL 16.9 smoke: `1 passed in 3.36s`, covering Alembic upgrade
  from the empty baseline, expected table inspection, and downgrade to base.

## API and data behavior

- Added `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and
  `GET /api/v1/me` with stable problem responses.
- Added Argon2id passwords, opaque hashed sessions/CSRF tokens, idle and
  absolute expiry, CSRF rotation, authorization-version invalidation, generic
  authentication failures, account lockout, safe audit metadata, and the exact
  `__Host-hr_session` cookie contract.
- Added typed global-role and job-grant policy functions that fail closed.
- Added explicit environment-driven system-admin bootstrap/rotation at
  `python -m server.app.identity.bootstrap`; no startup account is created.
- Added Nginx per-IP login limiting at an average of five requests per five
  minutes with a five-request burst.

## Migration

- `0002_identity_boundary` creates and reversibly drops organizations,
  departments, users, user roles, sessions, minimal jobs, job collaborators,
  and append-only application audit records.
- UUID keys, UTC-aware timestamps, foreign keys, normalized-email uniqueness,
  role/grant checks, membership uniqueness, and session indexes are included.
- No `create_all` is used by production startup or migration verification;
  test-only schema initialization is explicitly injected.

## Files/modules owned

- `server/app/identity/`
- `server/app/main.py`
- `server/migrations/env.py`
- `server/migrations/versions/0002_identity_boundary.py`
- `server/requirements*.txt`
- `server/tests/test_identity.py`, `test_policy.py`, `test_migrations.py`,
  `test_bootstrap.py`
- `deploy/nginx/default.conf`

## Commands and outputs

```text
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
=> 55 passed, 1 skipped in 7.81s

docker run ... postgres:16.9-alpine
docker run ... -e POSTGRES_SMOKE_URL=... ux09-server-test \
  python -m pytest server/tests/test_migrations.py -q
=> 1 passed in 3.36s

docker run --rm --add-host api:127.0.0.1 ... nginx:1.28.0-alpine nginx -t
=> syntax is ok; test is successful

docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
=> exit 0

git diff --check -- <Task 2 owned paths>
=> exit 0
```

## Self-review and concerns

- Reviewed API behavior, session invalidation, policy scope, migration reversal,
  runtime dependencies, Nginx configuration, secrets handling, and staged scope.
- Corrected the PostgreSQL sync driver runtime packaging and made unknown-user
  password verification consume the same Argon2 path during review.
- No blocking or non-blocking Task 2 concerns remain.
- Pre-existing modifications to `.superpowers/sdd/task-1-report.md` and
  `app/sample/candidates.csv` were not touched or staged.

## Security review remediation

Implementation commit: `e76993f`.

### RED evidence

- New focused tests initially reported 15 failures covering the invalid
  development `__Host-` cookie, missing Fetch Metadata and centralized CSRF
  enforcement, caller-trusted/unbound grants, missing bootstrap audits, and
  role/grant matrix violations.
- The trace-preservation regression then failed because middleware-generated
  CSRF denials omitted `X-Trace-ID` and request-completion handling.
- The first PostgreSQL hardening run exposed the expected immutable-audit
  database exception; the assertion was corrected to SQLAlchemy's PostgreSQL
  `OperationalError` wrapper while retaining update/delete rejection.
- The first rebuilt full suite exposed that the Docker test stage did not copy
  the Nginx config required by its security assertion; the test-stage-only copy
  was added without changing runtime image contents.

### Fixes

- PostgreSQL authentication now locks the selected user row before evaluating
  and updating failure state, serializing concurrent success/failure updates.
- `JobGrant` includes `user_id`; `AuthorizationService` loads only the current
  principal's organization/job grants and writes non-enumerating denial audits.
- The explicit role/grant matrix grants global recruiting access only to
  `recruiting_admin`, recruiter access through owner/recruiter grants, and
  hiring-manager access through manager grants.
- Migration `0003_identity_security_hardening` adds composite tenant keys/FKs
  for departments, users, sessions, jobs, owners, parents, and collaborators,
  plus an update/delete rejection trigger for append-only audit logs.
- Audits now cover login, logout denial/success, session invalidation,
  authorization denial, and bootstrap create/rotation without secrets or
  sensitive resource identifiers.
- Production uses secure `__Host-hr_session`; non-production HTTP uses the
  host-only `hr_session` cookie accepted by browsers.
- `GET /me` rejects explicit cross-site Fetch Metadata before rotating CSRF or
  idle expiry. Central middleware protects every state-changing `/api/v1`
  request, with login as the Origin-only exception.
- Audit network input uses Nginx-replaced `X-Real-IP`; tests assert Nginx replaces
  `X-Forwarded-For` with `$remote_addr` and never appends caller chains.
- Trailing blank lines were removed from the migration and policy tests.

### Final verification

```text
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
=> 69 passed, 5 skipped in 9.00s

PostgreSQL 16.9 isolated migration/invariant/concurrency gate:
python -m pytest server/tests/test_migrations.py server/tests/test_postgres_security.py -q
=> 5 passed in 17.45s

nginx:1.28.0-alpine nginx -t
=> syntax is ok; test is successful

docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
=> exit 0

git diff --check
=> exit 0
```

Concerns: none. This report update is intentionally unstaged scratch evidence.

## Final security review remediation

Implementation commit: `4f46779`.

### RED evidence

- Focused API/Nginx regressions initially failed 6 tests: missing and
  unrecognized `Sec-Fetch-Site` values and a disallowed `Origin` were accepted
  by `/me`; ten anonymous CSRF attempts created ten immutable audit rows; and
  no general Nginx API limit existed.
- The PostgreSQL independent-user regression failed at its two-party barrier,
  proving unrestricted `FOR UPDATE` serialized users through the joined
  organization row.

### Fixes

- CSRF denial audits now require a currently valid session and identified
  actor. Missing, unknown, revoked, expired, disabled, and stale-version
  sessions do not create audit rows; anonymous denials emit redacted structured
  telemetry containing only the trace identifier.
- Authenticated wrong-CSRF denials retain an immutable, non-enumerating audit
  event with no route, resource ID, or existence signal in metadata.
- `/api/v1/me` now requires `Sec-Fetch-Site` to be exactly `same-origin` or
  `same-site`; missing, cross-site, `none`, and unrecognized values fail before
  session mutation. A supplied `Origin` must also be allowlisted.
- Login locking now uses `with_for_update(of=User)`, preserving per-user
  lockout serialization without locking the joined organization row.
- Nginx applies a general per-IP `/api/` request limit while retaining the
  stricter exact login limit.

### Final verification

```text
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
=> 78 passed, 6 skipped in 13.30s

PostgreSQL 16.9 migration/invariant/concurrency gate:
python -m pytest server/tests/test_migrations.py server/tests/test_postgres_security.py -q
=> 6 passed in 22.55s

nginx:1.28.0-alpine nginx -t
=> syntax is ok; test is successful

docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
=> exit 0

git diff --check
=> exit 0
```

Concerns: none. This appended report evidence remains intentionally unstaged.

## Session lifecycle final remediation

Implementation commit: `8c7685e`.

### RED evidence

- The new state-changing-request regression failed for stale authorization,
  disabled-user, and expired sessions because CSRF validation returned false
  without revoking the known session or writing `session.invalidated`.
- The unknown-token control already persisted no session or audit rows,
  confirming the required distinction was specifically missing for known
  invalid sessions.

### Fix

- A single row-locking `_resolve_session` lifecycle helper now serves `/me`,
  logout, CSRF validation, and authenticated denial auditing.
- Existing invalid sessions are revoked exactly once with one of the
  non-sensitive reasons `idle_expired`, `absolute_expired`, `user_disabled`, or
  `authorization_version_stale`, and receive exactly one redacted
  `session.invalidated` audit event.
- Repeated presentation of the revoked session does not add another event.
  Missing cookies and unknown/random tokens remain actorless and persist no
  session or audit rows.

### Final verification

```text
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
=> 82 passed, 6 skipped in 13.58s

PostgreSQL 16.9 migration/invariant/concurrency gate:
python -m pytest server/tests/test_migrations.py server/tests/test_postgres_security.py -q
=> 6 passed in 23.24s

nginx:1.28.0-alpine nginx -t
=> syntax is ok; test is successful

docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
=> exit 0

git diff --check
=> exit 0
```

Concerns: none. This report evidence remains intentionally unstaged.
