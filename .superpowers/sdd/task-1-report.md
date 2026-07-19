# Task 1 Report: Phase 0 Server Runtime Foundation

## Result

Implemented the UX-09 Phase 0 FastAPI, worker, persistence-client, migration, logging,
health-check, and Docker Compose runtime foundation. The existing local application and
React prototype were not changed. `app/sample/candidates.csv` was neither modified by this
task nor staged.

## Files changed

- `server/app/`: application factory, health routes, trace middleware, redacted JSON logs,
  typed settings, SQLAlchemy async factories, MinIO factory/probe, and stoppable worker.
- `server/migrations/`, `server/alembic.ini`: Alembic async environment and empty baseline.
- `server/tests/`: deterministic health, trace, settings, redaction, and worker tests.
- `server/requirements*.txt`, `server/Dockerfile`, `server/README.md`: pinned Python 3.12
  runtime, build, test, migration, deployment, TLS, bucket, and secret instructions.
- `deploy/`: six-service Compose topology, private dependency network, proxy-only published
  port, health checks, restart policies, Nginx reverse proxy/static configuration, security
  headers, upload limit, and non-secret environment example.
- `.dockerignore`: excludes unrelated application data and local environments from images.

## TDD evidence

### RED

Command:

```powershell
python -m pytest server/tests -q
```

Observed: collection failed in four test modules because the required `server.app` package
did not exist.

Self-review regression RED:

```powershell
python -m pytest server/tests/test_settings.py::test_production_accepts_explicit_origins_and_non_placeholder_secrets -q
```

Observed: failed because placeholder detection incorrectly rejected a valid password.

Worker recovery RED:

```powershell
python -m pytest server/tests/test_worker.py::test_worker_keeps_running_when_a_readiness_check_fails -q
```

Observed: the worker task exited on the first readiness exception; the interrupted run was
stopped and the worker loop was changed to retry safely without logging exception contents.

### GREEN

```powershell
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
```

Observed under Python 3.12.11 with the pinned dependencies: `15 passed in 0.57s`.

Audit regression RED:

```powershell
python -m pytest server/tests/test_settings.py::test_production_rejects_insecure_cors_origin -q
```

Observed: failed because production accepted an `http://` CORS origin. After requiring HTTPS
origins in production, the focused test passed.

## Verification commands and output summary

- `docker info --format '{{.ServerVersion}}'` -> Docker Engine 29.4.3 available.
- `docker build --target test -t ux09-server-test -f server/Dockerfile .` -> Python 3.12.11
  test image built with the pinned runtime and development dependencies.
- `docker run --rm ux09-server-test` -> 15 passed in 0.57s.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet`
  -> exit 0.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml build api`
  -> the explicit `runtime` target built successfully; image user is `65532:65532`.
- `docker run --rm ux09-server-test python -m alembic -c server/alembic.ini upgrade head --sql`
  -> empty baseline SQL generated successfully.
- Rendered Compose topology inspection -> only `proxy` publishes one port and joins `edge`;
  all six services join `private`, which is marked internal.
- `git diff --cached --check` -> no errors before the final commit.

## Self-review findings addressed

- Narrowed placeholder detection so strong values containing the word `password` are valid.
- Made Alembic paths independent of the caller's working directory.
- Preserved `/api/` when Nginx forwards requests.
- Added a public edge network only to the proxy while dependencies remain on an internal
  network.
- Added an explicit Python 3.12 Docker test target and pinned the Compose application build to
  the non-root runtime target so test dependencies/root execution cannot leak into production.
- Rejected non-HTTPS CORS origins in production while preserving localhost HTTP development.
- Kept the worker alive across transient readiness failures so it can receive SIGTERM and
  recover when dependencies return.
- Excluded the unrelated application and local virtual environment from Docker build context.

## Commit

Implementation commits:

- `8f5a3e6` (`Bootstrap UX-09 server runtime`).
- `69c5333` (`Harden UX-09 runtime verification`) — final audited Task 1 commit.

## Concerns

- The private MinIO bucket must be provisioned before `/health/ready` becomes 200; this is
  documented and the application deliberately does not create public bucket policy.
- This audit validated deterministic tests, image construction, migration SQL, and rendered
  topology. It did not repeat a stateful six-service startup because the brief specifically
  requires Compose syntax validation and the readiness behavior is dependency-injected in tests.

## Review fixes: 2026-07-12

Commit: `4089199` (`Address UX-09 runtime review findings`).

### RED evidence

```powershell
python -m pytest server/tests/test_settings.py::test_production_rejects_database_url_without_password server/tests/test_observability.py::test_redact_matches_sensitive_key_fragments server/tests/test_health.py::test_ready_health_times_out_hanging_probes server/tests/test_worker.py::test_worker_entrypoint_configures_structured_logging server/tests/test_worker.py::test_worker_shutdown_is_bounded_when_probe_hangs -q
```

Observed: 6 failures. Production accepted missing database passwords; redaction missed compound
sensitive keys; readiness timeout settings and worker deadlines did not exist; and the worker
entrypoint did not expose structured logging initialization.

### GREEN evidence

The same focused command passed: `6 passed in 0.79s`.

```powershell
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
git diff --check
```

Observed: the Python 3.12.11 image built successfully; the complete suite passed with
`21 passed in 0.65s`; Compose config exited 0; and `git diff --check` reported no whitespace
errors, only the pre-existing `app/sample/candidates.csv` line-ending warning.

### Fix summary

- Production settings now require a non-empty database URL password.
- API and worker readiness checks share a configurable positive deadline; hanging probes are
  cancelled and the worker can complete SIGTERM shutdown within the bound.
- Worker startup configures the shared structured, recursively redacted JSON logger.
- Redaction matches sensitive fragments in compound key names.
- Backup files are published atomically only after successful non-empty dumps, and health now
  requires a non-empty backup artifact newer than 25 hours.
- Removed the six reported trailing blank lines.

## Second review fixes: 2026-07-12

Commit: `07a8a76` (`Bound UX-09 storage readiness`).

### RED evidence

```powershell
docker build --target test -t ux09-server-test-red -f server/Dockerfile .
docker run --rm ux09-server-test-red python -m pytest server/tests/test_settings.py::test_production_rejects_decoded_placeholder_database_password server/tests/test_probes.py server/tests/test_storage.py -q
```

Observed: collection failed because structured concurrent `check_readiness` did not exist.
Running the credential and real-storage groups separately produced `8 failed, 2 passed`:
decoded/compound placeholders were accepted, the storage factory had no timeout parameters,
and the real MinIO probe had no short network deadline.

### GREEN evidence

```powershell
docker run --rm ux09-server-test python -m pytest server/tests/test_settings.py::test_production_rejects_decoded_placeholder_database_password server/tests/test_probes.py server/tests/test_storage.py -q
```

Observed: `11 passed in 0.42s` under Python 3.12.11.

```powershell
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
git diff --check
```

Observed: full Python 3.12 suite `32 passed in 0.68s`; Compose config exited 0; and
`git diff --check` reported no Task 1 whitespace errors, only the pre-existing CSV
line-ending warning.

### Fix summary

- Production validation now structurally parses the database URL, percent-decodes the password,
  and rejects values equal to or containing `secret`, `password`, `change-me`, `changeme`,
  `placeholder`, or `example`.
- Readiness probes run in an `asyncio.TaskGroup`, so a failing async probe cancels its sibling.
- The real MinIO client now uses explicit 1-second connect, 3-second read, and 4-second total
  urllib3 deadlines with retries disabled. A socket-level test verifies the synchronous
  `bucket_exists` operation returns within its configured read bound.
- Worker shutdown remains bounded by the 5-second readiness deadline. Documentation explicitly
  states async cancellation does not instantly terminate an OS thread; the underlying MinIO
  network timeout is the finite thread-operation bound.

## Review fixes: shared Nginx route validator

Commit: final amended commit (`fix: enforce shared nginx root routes`); hash is reported in the task response.

### Fix summary

- Restricted upstream validation to the structured `location /` block for each named server.
- Restricted `proxy_pass` matching to directives directly declared in that root location,
  excluding nested location or conditional blocks.
- Added a regression test proving a correct upstream in `/health` cannot satisfy the root route.
- Added a CLI success-path test asserting exit code `0` and empty stderr.

### RED evidence

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
```

Observed: `1 failed, 6 passed`; the non-root upstream regression expected
`wrong_upstream:hr.aurora-tek.cn` but the old implementation returned no errors.

### GREEN evidence

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
python -m py_compile deploy/shared_nginx_release_validator.py
```

Observed: `7 passed in 0.24s`; `py_compile` exited `0` with no output.

### Self-review

- The validator now requires a precise root location and direct root-level upstream.
- Nested brace blocks are preserved during extraction and excluded from direct directive checks.
- The CLI success contract is explicitly covered and emits no stderr on valid input.
- `git diff --check` passed before commit.

### Concerns

None identified.
