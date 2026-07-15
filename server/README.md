# UX-09 server runtime

Python 3.12 is required. The existing `app/web_app.py` remains a separate local tool.

## Local tests

The reproducible test path uses the project's Python 3.12 Docker target:

```powershell
docker build --target test -t ux09-server-test -f server/Dockerfile .
docker run --rm ux09-server-test
```

When a local Python 3.12 interpreter is available, installing
`server/requirements-dev.txt` and running `python -m pytest server/tests` is equivalent.

## Migrations

From the repository root, set `DATABASE_URL` to the async PostgreSQL URL for the
bootstrap/migration owner (`POSTGRES_USER`), not the runtime application role:

```powershell
python -m alembic -c server/alembic.ini upgrade head
```

The Phase 0 revision is intentionally empty; domain tables arrive in later tasks.

Alembic never creates roles or stores database passwords. PostgreSQL bootstrap owns the
schema, while API and worker processes connect as the separate `APP_DB_USER`. On a fresh
Compose volume, `deploy/postgres/provision-app-role.sh` creates that login with
`NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS` and establishes default
table/sequence privileges. After every migration on an existing volume, rerun the safe,
idempotent grant reconciliation before restarting API/worker processes:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T postgres `
  sh /docker-entrypoint-initdb.d/10-provision-app-role.sh
```

The application role receives DML on current non-audit tables, append-only access to audit
tables, and no function grants. The separate `GOVERNANCE_DB_USER` login receives no table or
sequence privileges and inherits only the fixed, no-login `ux09_governance_executor` boundary,
which can execute `redact_candidate_data(uuid, uuid, uuid)`. Keep the owner, application, and
governance usernames and passwords pairwise distinct. The provisioning script rejects shared
values, removes stale inbound/outbound governance memberships, and reconciles all three roles
idempotently after migrations. Reconciliation also removes any inherited `ADMIN OPTION` before
restoring the single ordinary executor membership, so the governance login cannot delegate it.

The API container receives none of the governance database, object-deletion, ledger, or signing
settings. The general worker continues to use `DATABASE_URL` for normal queue work and receives a
separate `GOVERNANCE_DATABASE_URL` for the later deletion handler. Task B2B1 does not register or
run that handler.

## Compose

Copy `deploy/.env.example` to `deploy/.env`, replace every `change-me` value, then run:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build -d
```

Compose first runs the one-shot `minio-provision` service. MinIO root credentials exist only in
the MinIO server and that provisioner; API and worker runtime use the ordinary application object
credential. The deletion credential can list/delete only configured resume/export prefixes and
cannot read or write objects. The ledger credential can list/read/write only its ledger prefix and
cannot delete or access resume/export objects. Report exports use the ordinary object bucket under
`exports/`, so `GOVERNANCE_EXPORT_BUCKET` must match `OBJECT_STORAGE_BUCKET` and the deletion
prefix must remain `exports/` unless the report storage contract changes with it.
All configured governance prefixes are non-empty relative paths ending in `/`. Retired MinIO
users are ignored only when `mc` explicitly reports that the user does not exist; authentication,
network, or CLI failures stop provisioning without printing the retired key or command output.

`server.app.governance.storage` provides the delete-only adapter and canonical signed ledger v1.
Ledger writes verify an existing object before accepting idempotent re-entry; malformed, tampered,
or mismatched evidence fails with a stable non-identifying code. Ledger bodies contain only schema
version, organization/request/candidate UUIDs, completion time, manifest hash, exact object keys,
database-redaction checksum, and HMAC signature.

Validate the example topology without starting services:

```powershell
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
```

The backend verification gate is deliberately layered because the test image does not contain a
Docker CLI. Run the backend suite inside the PostgreSQL-enabled test container with exactly:

```text
python -m pytest server/tests --ignore=server/tests/test_production_topology.py --ignore=server/tests/test_observability_topology.py -q
```

Run both Docker/Compose topology files on the host, where the Docker CLI is available:

```powershell
python -m pytest server/tests/test_production_topology.py server/tests/test_observability_topology.py -q
```

These two commands form the complete gate; do not describe the container command alone as the
standard full backend suite.

Only Nginx publishes a host port. Development uses HTTP on `http://localhost:8080`.

Outbox delivery is at-least-once. Every allowlisted topic handler receives the durable
`outbox_events.id` UUID as its mandatory idempotency key. External side effects must use
that key for deduplication because a crash after the side effect and before publication
can replay the same event. The system does not claim externally exactly-once delivery.
When shutdown arrives while a database claim is in flight, the worker does not start the
returned item. It intentionally leaves the lease untouched; database-time lease expiry
and stale-claim recovery make the same durable ID available to another worker.
Production TLS must terminate upstream or use externally managed certificates mounted into
Nginx with a production-specific server block. Never expose API, PostgreSQL, or MinIO ports.

Readiness probes run concurrently and cancel siblings after a failure. The worker dependency
cycle is bounded by `READINESS_TIMEOUT_SECONDS` (5 seconds by default). MinIO uses explicit
1-second connect, 3-second read, and 4-second total network deadlines with retries disabled.
Cancelling the async wrapper does not stop a running OS thread instantly; the underlying MinIO
network deadline provides the finite bound required for worker process shutdown.

## Production requirements

Set `APP_ENVIRONMENT=production`, distinct non-placeholder PostgreSQL owner and application
passwords, distinct MinIO
access and secret keys, and explicit HTTPS CORS origins. Startup rejects placeholders and
wildcard CORS. Credential values beginning with `change-me`, `placeholder`, or `replace-me`
(including suffixed example values) are rejected without echoing the value. Buckets are private and must be provisioned separately; the application never
enables anonymous/public access. Rotate secrets through the deployment environment, not Git.

Rotate governance credentials through the deployment secret store. Stop the governance deletion
consumer, rerun PostgreSQL role and MinIO policy provisioning with the new values, deploy worker
secrets atomically, and run the real PostgreSQL and MinIO smoke tests before resuming work. When
rotating MinIO access-key identities, set `PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY` and/or
`PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY` for the provisioning run; the provisioner removes those
retired users after attaching the new least-privilege policies. Production requires the independent
ledger signing key to contain at least 32 UTF-8 bytes, no whitespace or placeholder text, and
non-trivial character diversity.
Signing-key rotation requires explicit ledger key history/versioning; it is not a safe online
single-key swap because prior ledgers must remain independently verifiable.

Candidate contacts require separate high-entropy 32-byte base64url
`CONTACT_ENCRYPTION_KEY` and `CONTACT_LOOKUP_SECRET` values. Generate them independently;
the encryption value is a Fernet key and neither value is committed. Rotation is an offline
maintenance boundary: stop writes, decrypt and re-encrypt all
contacts, recompute lookup hashes, reconcile row counts and duplicate constraints, then deploy
both new values atomically. Online dual-key rotation is outside Phase 2.

LLM provider API keys use another independent high-entropy 32-byte base64url
`LLM_CONFIG_ENCRYPTION_KEY`. Deployment operators define the available providers and models
with `LLM_PROVIDER_ALLOWLIST_JSON`; system administrators can select only these IDs and cannot
submit a Base URL. For example:

```text
LLM_PROVIDER_ALLOWLIST_JSON={"openai":{"base_url":"https://api.openai.com/v1","models":["gpt-4.1-mini"]}}
```

Production provider URLs must use HTTPS on port 443. Connection tests resolve and validate all
provider addresses, pin one public address for the TLS request, reject redirects, and send only a
constant health-check prompt. No JD or resume content is sent by the settings connection test.

When LLM evaluation is enabled, an empty job allowlist applies to every job in the tenant; a
non-empty list limits evaluation to those job IDs. Deterministic rule results remain authoritative
fallback facts. LLM failure never changes an application stage and leaves the run partially
completed with a safe error code. Successful bounded LLM facts are stored separately and exposed
without prompts, provider bodies, input hashes, or API keys.

Before evaluation, the worker removes recognized email/phone values, labeled name/address fields,
and the known candidate display name, then applies strict input limits. This deterministic
redaction is not a general DLP guarantee. Deploy only an approved provider that satisfies the
organization's privacy and data-processing requirements.

Candidate notes are append-only MVP facts, matching JD, rule, resume, stage-event, and
candidate-event history. Corrections create a new note/event instead of editing prior text.
