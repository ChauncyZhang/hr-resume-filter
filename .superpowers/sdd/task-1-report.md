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
python -m pytest server/tests -q
```

Observed: `14 passed in 0.66s`.

## Verification commands and output summary

- `python -m pytest server/tests -q` -> 14 passed.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet`
  -> exit 0.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml build api`
  -> Python 3.12 image and pinned production dependencies built successfully.
- `docker run --rm ux09-api python -m alembic -c server/alembic.ini upgrade head --sql`
  -> empty baseline SQL generated successfully.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml up -d` -> all six
  required services created; PostgreSQL, MinIO, and API became healthy. The stack was stopped
  with `docker compose ... down` after inspection.
- `git diff --check` -> no errors; Git emitted only the pre-existing CSV line-ending warning.

## Self-review findings addressed

- Narrowed placeholder detection so strong values containing the word `password` are valid.
- Made Alembic paths independent of the caller's working directory.
- Preserved `/api/` when Nginx forwards requests.
- Added a public edge network only to the proxy while dependencies remain on an internal
  network.
- Kept the worker alive across transient readiness failures so it can receive SIGTERM and
  recover when dependencies return.
- Excluded the unrelated application and local virtual environment from Docker build context.

## Commit

Implementation commit: `8f5a3e6` (`Bootstrap UX-09 server runtime`).

## Concerns

- The host only has Python 3.14, so the pinned Python 3.12 dependencies could not be installed
  in the local virtual environment; unit tests ran with the host's compatible FastAPI/Pydantic
  packages, while the production dependency set was verified by the successful Python 3.12
  Docker build.
- Compose startup was not repeated after the final proxy edge-network and worker retry fixes,
  per the instruction to stop long-running commands. Compose syntax and all local tests pass.
- The private MinIO bucket must be provisioned before `/health/ready` becomes 200; this is
  documented and the application deliberately does not create public bucket policy.
