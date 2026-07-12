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
