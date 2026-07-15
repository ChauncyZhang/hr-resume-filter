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

## Independent review remediation

The Phase 6A review findings were addressed without modifying the base Compose
or any backend, Worker, Dockerfile, README, migration, MinIO, frontend, or
user-owned file.

- The production overlay now forces `APP_ENVIRONMENT=production` for both API
  and Worker, and the fully merged model test asserts both effective values.
- `SERVER_NAME` is now required during Compose interpolation instead of falling
  back to a wildcard/default name.
- `deploy/production-preflight.sh` parses `docker compose version --short`,
  rejects versions below 2.24.4 before any config call, and always validates the
  hard-coded base-plus-production-overlay model. Its test records the actual
  config invocation and proves both files are present, so there is no base-only
  fallback.
- Each merged-model run supplies a unique synthetic governance sentinel across
  every governance-related deployment input and proves that no API environment
  value or URL contains it.
- A temporary running Nginx container now receives real HTTPS requests for both
  `/metrics` and `/metrics/child`; both must return 404.
- The Nginx syntax and runtime tests read the proxy image from the fully merged
  Compose model rather than hard-coding an image version in test code.

### Review-fix TDD evidence

The expanded focused suite was run before production changes and reported five
failures: API remained in development, `SERVER_NAME` was optional, and the
preflight did not exist. The existing runtime metrics behavior and merged-image
syntax gate passed under the stronger tests.

After the minimal implementation, the first GREEN run reported `7 passed, 2
failed`; both failures identified a Git awk portability error caused by using
the built-in name `index` as a function parameter. Renaming that local variable
closed the Linux-shell portability defect.

Final focused run:

```text
python -m pytest server/tests/test_production_topology.py -q
9 passed in 8.58s
```

### Review-fix verification

Fake Compose version gates:

```text
python -m pytest server/tests/test_production_topology.py::test_preflight_rejects_compose_older_than_minimum_before_config server/tests/test_production_topology.py::test_preflight_accepts_minimum_version_and_validates_merged_model -q
2 passed in 1.70s
```

The 2.24.3 fake exits before config; the 2.24.4 fake invokes real Compose and
the test verifies that both `deploy/compose.yaml` and
`deploy/compose.production.yaml` were passed.

Installed Compose gate:

```text
python -m pytest server/tests/test_production_topology.py::test_preflight_accepts_installed_compose_and_validates_merged_model -q
1 passed in 1.63s
```

Merged-image disposable-certificate syntax gate:

```text
python -m pytest server/tests/test_production_topology.py::test_rendered_production_nginx_passes_nginx_t_with_disposable_certificate -q
1 passed in 2.17s
```

Additional commands all exited zero:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/production-preflight.sh

$env:HTTPS_BIND_ADDRESS='127.0.0.1'
$env:HTTPS_PORT='443'
$env:SERVER_NAME='recruiting.example.test'
$env:TLS_CERTIFICATE_PATH=(Resolve-Path 'deploy/nginx/production.conf.template').Path
$env:TLS_PRIVATE_KEY_PATH=(Resolve-Path 'deploy/nginx/snippets/security-headers.conf').Path
docker compose --env-file deploy/.env.example -f deploy/compose.yaml -f deploy/compose.production.yaml config --quiet
```

The final pre-commit focused rerun reported `9 passed in 6.47s`. After staging
only the four review-fix files, the following owned-scope whitespace gate also
exited zero:

```text
git diff --cached --check -- deploy/compose.production.yaml deploy/production-preflight.sh server/tests/test_production_topology.py .superpowers/sdd/task-phase6a-report.md
```

### Remaining review-fix risks

- The preflight validates configuration and minimum Compose capability; it does
  not pull images, start services, validate production certificate trust, or
  perform a live deployment smoke test.
- The real-request Nginx test uses an ephemeral local port and disposable
  self-signed certificate. External firewall, DNS, load-balancer, CA renewal,
  and production host routing remain deployment-environment responsibilities.
