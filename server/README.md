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

From the repository root, with `DATABASE_URL` set to an async PostgreSQL URL:

```powershell
python -m alembic -c server/alembic.ini upgrade head
```

The Phase 0 revision is intentionally empty; domain tables arrive in later tasks.

## Compose

Copy `deploy/.env.example` to `deploy/.env`, replace every `change-me` value, then run:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build -d
```

Validate the example topology without starting services:

```powershell
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet
```

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

Set `APP_ENVIRONMENT=production`, a non-placeholder PostgreSQL password, distinct MinIO
access and secret keys, and explicit HTTPS CORS origins. Startup rejects placeholders and
wildcard CORS. Buckets are private and must be provisioned separately; the application never
enables anonymous/public access. Rotate secrets through the deployment environment, not Git.

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
