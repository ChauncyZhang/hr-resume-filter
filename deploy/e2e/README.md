# Phase 3 restart-recovery acceptance

This harness starts an isolated copy of the production-shaped Compose stack, seeds only synthetic data, drives the real React/Vite client with Playwright, and proves that a run queued while the worker is stopped survives browser closure and an API restart without duplicate durable facts.

## Safety and isolation

- Every invocation uses a unique Compose project, host ports, PostgreSQL volume, MinIO volume, and browser profile.
- Test credentials and encryption keys are generated in process memory and are not written to the repository.
- The harness never targets an existing Compose project and never uses production environment files.
- Successful runs remove containers and volumes. Failed runs keep them only when `-KeepOnFailure` is supplied.

## Acceptance contract

1. Migrate an empty PostgreSQL database and create the private MinIO bucket.
2. Seed one recruiting administrator and one job with immutable JD and rule versions.
3. Stop the worker, upload 100 distinct synthetic TXT resumes through the browser UI, and persist the generated run ID in the application's own recent-task local storage.
4. Prove all 100 items are durable and unprocessed, close the browser, restart `api`, start `worker`, and reopen the same persistent browser profile.
5. Resume the same run from the recent-task banner and wait for a terminal result.
6. Query PostgreSQL for the run and require exactly 100 items, candidates, `new` applications, and screening results, with no duplicate item IDs or queue dedupe keys; then stat all 100 recorded objects in the private MinIO bucket.

## Run

From the repository root:

```powershell
PowerShell -ExecutionPolicy Bypass -File deploy/e2e/run-recovery.ps1
```

Keep the isolated stack after a failure:

```powershell
PowerShell -ExecutionPolicy Bypass -File deploy/e2e/run-recovery.ps1 -KeepOnFailure
```

The script prints the generated Compose project name and diagnostic commands. Do not copy generated credentials from process environments or container inspection into tickets or logs.

## Rollback and cleanup

This harness has no production rollback action. Its rollback is deletion of the unique Compose project and volumes:

```powershell
docker compose -p <printed-project> -f deploy/compose.yaml -f deploy/e2e/compose.yaml down --volumes --remove-orphans
```

Production application rollback must retain PostgreSQL and MinIO data, deploy the previous compatible image, and must not run an automatic Alembic downgrade.
