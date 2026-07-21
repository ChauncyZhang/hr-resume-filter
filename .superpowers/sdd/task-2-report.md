# Task 2 Report: Shared Nginx Release Protection

## Status

Completed and committed.

## Change Files

- `deploy/remote-release.sh`
- `deploy/remote-rollback.sh`
- `deploy/shared-nginx-smoke.sh`
- `deploy/tests/test_remote_deploy_scripts.py`

## Commit

`77e9e21 fix: preserve website routes during recruitment deploys`

## RED Evidence

Before implementation:

```text
python -m pytest deploy/tests/test_remote_deploy_scripts.py -q -p no:cacheprovider
...FFF..
3 failed, 5 passed
```

The expected failures proved the release script did not contain
`production.conf.template` inheritance and neither deployment script referenced
`shared-nginx-smoke.sh`. The initial fake-command fixture used Windows symlink
creation and Git Bash PATH handling that could fail before exercising release
logic; it was corrected to use fake `readlink` and a POSIX PATH injected by
Git Bash. The final RED rerun after fixture correction reported the two missing
source contracts (`2 failed, 6 passed`); the fake-command test was then made to
reach the release path and verify marker-failure rollback behavior.

## GREEN Evidence

Implemented:

- Release inherits `.env`, Compose HTTPS overlay, and the previous healthy
  `production.conf.template` before validator and Compose configuration checks.
- Release and rollback capture the `aurora-web` ID, validate both shared-network
  attachments, run `proxy nginx -t`, and invoke a bounded three-domain smoke
  before switching `current`.
- `shared-nginx-smoke.sh` rejects an empty marker, never writes response bodies,
  verifies unchanged website container identity, and checks HR readiness, HR
  root, apex website provenance, and `www` website provenance.
- The fake-command test proves a failed website marker triggers
  `rollback_services` and that no recorded Compose invocation contains
  `aurora-web`.
- Calls use `sh shared-nginx-smoke.sh` so the new script does not depend on an
  executable mode during release transfer or rollback of an older release.

## Test Commands And Results

```powershell
python -m pytest deploy/tests/test_remote_deploy_scripts.py deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
# 15 passed in 1.48s

& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-release.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-rollback.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/shared-nginx-smoke.sh
# all exited 0

git diff --check
# exited 0
```

## Self-Review

- No `--remove-orphans` appears in Task 2 scripts.
- No Compose command operates on `aurora-web`; it is only inspected.
- Release rollback restores only the previous `beyondcandidate` project proxy
  or project services, and does not modify shared website container lifecycle.
- Rollback validates the target release inherited template and Compose config
  before services start; both release and rollback update `current` only after
  Nginx, network, ID, and runtime smoke checks pass.
- No server `.env`, overlay, certificate, or production template was committed.

## Concerns

- Local verification uses fake Docker and curl commands, not production Docker
  or public domains. Production promotion must still review its runtime smoke
  output and the configured non-empty `AURORA_WEB_SMOKE_MARKER`.

## DevOps Review Remediation

### RED Evidence

```text
python -m pytest deploy/tests/test_remote_deploy_scripts.py deploy/tests/test_shared_nginx_smoke.py -q -p no:cacheprovider
.....FF...F..
3 failed, 10 passed
```

The failures proved that rollback used the previous release smoke tool, release
had no automatic-rollback revalidation helper, and apex/www smoke requests did
not use bounded redirect following.

### GREEN Evidence

- Rollback now executes the smoke tool packaged with the calling current
  release, so rollback from the Task 2 release to a `f6be6dc`-shape target with
  no smoke script succeeds.
- Candidate failure restores the previous project services and rechecks proxy
  health, `nginx -t`, both shared-network attachments, unchanged `aurora-web`
  ID, and the full three-domain smoke. Failed restoration verification emits
  `rollback verification failed; previous release is not healthy` and exits
  non-zero.
- The real repository `deploy/shared-nginx-smoke.sh` is executed by fake
  Docker/curl tests. It covers all domains, empty marker, marker mismatch,
  network and identity checks, bounded timeout flags, and apex/www redirects.
- Apex and `www` requests now use `--location --max-redirs 3` while retaining
  `--fail --silent --show-error`, connect timeout, total timeout, and body-free
  marker matching.

### Commands And Results

```powershell
python -m pytest deploy/tests/test_remote_deploy_scripts.py deploy/tests/test_shared_nginx_smoke.py deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
# 21 passed in 4.48s

& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-release.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-rollback.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/shared-nginx-smoke.sh
git diff --check
# all exited 0
```

### Review

- No `--remove-orphans` was added.
- `aurora-web` remains inspected only; no Compose command targets it.
- The legacy rollback regression intentionally omits the target release smoke
  script and verifies the four real smoke curl calls from the current release
  tool.
