# UX-09 server runtime

Python 3.12 is required. The existing `app/web_app.py` remains a separate local tool.

## Local tests

```powershell
python -m venv server/.venv
server/.venv/Scripts/python -m pip install -r server/requirements-dev.txt
server/.venv/Scripts/python -m pytest server/tests
```

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

Only Nginx publishes a host port. Development uses HTTP on `http://localhost:8080`.
Production TLS must terminate upstream or use externally managed certificates mounted into
Nginx with a production-specific server block. Never expose API, PostgreSQL, or MinIO ports.

## Production requirements

Set `APP_ENVIRONMENT=production`, a non-placeholder PostgreSQL password, distinct MinIO
access and secret keys, and explicit HTTPS CORS origins. Startup rejects placeholders and
wildcard CORS. Buckets are private and must be provisioned separately; the application never
enables anonymous/public access. Rotate secrets through the deployment environment, not Git.
