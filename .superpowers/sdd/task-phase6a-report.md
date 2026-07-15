# Phase 6A implementation report

## Status

Implemented the production-only HTTPS overlay and topology gate within the five
owned files. The base development Compose, backend, Worker, migrations, MinIO
provisioning, Dockerfile, README, and pre-existing user-owned files were not
modified or staged by this task.

## Files

- `deploy/compose.production.yaml`
- `deploy/nginx/production.conf.template`
- `deploy/nginx/snippets/security-headers.conf`
- `server/tests/test_production_topology.py`
- `.superpowers/sdd/task-phase6a-report.md`

## Behavior

- The fully merged production model replaces the development port mapping with
  one published TCP HTTPS entry on the proxy and leaves every other service
  without host ports.
- TLS certificate and private-key files are read-only bind mounts at fixed
  container paths. Only server-name substitution is enabled in the Nginx
  template; private-key material is not passed through container environment or
  browser assets.
- Nginx accepts TLS 1.2 and 1.3, keeps the same-origin API, login throttling,
  trace headers, health proxy, 10 MiB upload limit, and SPA fallback, and returns
  404 for `/metrics` and its descendants.
- HSTS, nosniff, frame denial, no-referrer, Permissions-Policy, and the required
  CSP directives are applied. The HTML shell is served with `Cache-Control:
  no-store`.
- The merged-model test also proves that the API service does not receive the
  governance database, object-deletion, ledger, or signing settings.

## TDD evidence

Initial RED:

```text
python -m pytest server/tests/test_production_topology.py -q
4 failed in 0.68s
```

All four tests failed because the owned production overlay, template, and
security-header files did not yet exist.

First GREEN iteration produced three passes and one expected integration
failure: standalone `nginx -t` could not resolve the Compose-only `api` DNS
name. The disposable test container was then given a test-only loopback mapping
for `api`; production proxy behavior was unchanged.

The envsubst restriction was separately driven RED:

```text
python -m pytest server/tests/test_production_topology.py::test_merged_production_topology_mounts_tls_files_without_api_privilege_leak -q
1 failed in 0.46s
```

The merged proxy environment lacked `NGINX_ENVSUBST_FILTER`; the overlay now
restricts substitution to the template's only placeholder, `SERVER_NAME`.

Final focused gate:

```text
python -m pytest server/tests/test_production_topology.py -q
4 passed in 1.42s
```

This run generated a one-day disposable self-signed RSA certificate and passed
`nginx -t` in `nginx:1.28.0-alpine`.

## Additional verification

```powershell
$env:HTTPS_BIND_ADDRESS='127.0.0.1'
$env:HTTPS_PORT='443'
$env:SERVER_NAME='recruiting.example.test'
$env:TLS_CERTIFICATE_PATH=(Resolve-Path 'deploy/nginx/production.conf.template').Path
$env:TLS_PRIVATE_KEY_PATH=(Resolve-Path 'deploy/nginx/snippets/security-headers.conf').Path
docker compose --env-file deploy/.env.example -f deploy/compose.yaml -f deploy/compose.production.yaml config --quiet
```

Result: exit code 0. The disposable paths are used only for Compose model
validation and contain no certificate, key, password, or secret material.

## Concerns

- The syntax gate proves that a disposable certificate and the rendered Nginx
  configuration load successfully; it does not validate a production CA chain,
  hostname, renewal automation, or live TLS handshake.
- The overlay uses Compose `!override` so the development port and volume lists
  are replaced instead of appended. Production tooling must use a Compose
  release that supports this merge tag.
- HSTS includes subdomains. The production server name and certificate scope
  must be reviewed before first exposure because clients cache this policy.
