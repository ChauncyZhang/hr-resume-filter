# Shared Nginx Release Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every recruitment-system release inherit and validate the production shared Nginx configuration so deploying `hr.aurora-tek.cn` cannot overwrite or restart the `aurora-tek.cn` website.

**Architecture:** Keep the currently healthy release as the source of truth for the shared Nginx template and server-specific HTTPS Compose overlay. A focused validator checks the inherited routing contract, while release and rollback scripts perform symmetric runtime checks for all three domains, the shared Docker network, Nginx syntax, and the unchanged `aurora-web` container identity.

**Tech Stack:** Bash, Python 3.12, Docker Compose, Nginx, PowerShell, pytest

## Global Constraints

- The release must preserve `hr.aurora-tek.cn`, `aurora-tek.cn`, and `www.aurora-tek.cn`.
- The website upstream remains exactly `http://aurora-web:3000`; the recruitment API upstream remains exactly `http://api:8000`.
- `aurora-web` and the proxy must remain connected to `beyondcandidate_edge`.
- Never use `docker compose --remove-orphans`.
- A recruitment release or rollback must not stop, recreate, rename, or delete `aurora-web`.
- Do not commit the production certificate, server `.env`, server-specific Compose overlay, or the inherited shared Nginx template.
- The repository's single-domain `deploy/nginx/production.conf.template` remains a bootstrap template, not the production shared-config source.

---

### Task 1: Validate The Inherited Shared Routing Contract

**Files:**
- Create: `deploy/shared_nginx_release_validator.py`
- Create: `deploy/tests/test_shared_nginx_release_validator.py`

**Interfaces:**
- Consumes: UTF-8 Nginx template path supplied with `--nginx-template`.
- Produces: `validate_nginx_template(text: str) -> list[str]` and CLI exit code `0` only when the HR domain routes to the API and both website domains route to `aurora-web`.

- [ ] **Step 1: Write failing contract tests**

```python
from deploy.shared_nginx_release_validator import validate_nginx_template


def test_accepts_shared_hr_and_website_routes():
    text = """
    server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }
    server { server_name aurora-tek.cn www.aurora-tek.cn; location / { proxy_pass http://aurora-web:3000; } }
    """
    assert validate_nginx_template(text) == []


def test_rejects_template_that_drops_website_route():
    text = "server { server_name hr.aurora-tek.cn; location / { proxy_pass http://api:8000; } }"
    assert validate_nginx_template(text) == [
        "missing_server_name:aurora-tek.cn",
        "missing_server_name:www.aurora-tek.cn",
    ]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
```

Expected: collection fails because `deploy.shared_nginx_release_validator` does not exist.

- [ ] **Step 3: Implement deterministic validation and CLI output**

```python
def validate_nginx_template(text: str) -> list[str]:
    blocks = extract_server_blocks(text)
    routes = [
        ("hr.aurora-tek.cn", "http://api:8000"),
        ("aurora-tek.cn", "http://aurora-web:3000"),
        ("www.aurora-tek.cn", "http://aurora-web:3000"),
    ]
    errors = []
    for name, upstream in routes:
        named = [block for block in blocks if name in server_names(block)]
        if not named:
            errors.append(f"missing_server_name:{name}")
        elif not any(f"proxy_pass {upstream};" in block for block in named):
            errors.append(f"wrong_upstream:{name}")
    return errors
```

`extract_server_blocks` must use brace-depth scanning so nested `location` blocks remain attached to their outer `server` block; `server_names` must parse only the `server_name ...;` directive. The CLI must print only stable error codes to stderr and must not print template contents.

- [ ] **Step 4: Run validator tests and syntax check**

Run:

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
python -m py_compile deploy/shared_nginx_release_validator.py
```

Expected: all tests pass and `py_compile` exits `0`.

- [ ] **Step 5: Commit the validator**

```powershell
git add deploy/shared_nginx_release_validator.py deploy/tests/test_shared_nginx_release_validator.py
git commit -m "feat: validate shared production nginx routes"
```

---

### Task 2: Preserve Shared Configuration During Release And Rollback

**Files:**
- Modify: `deploy/remote-release.sh`
- Modify: `deploy/remote-rollback.sh`
- Create: `deploy/shared-nginx-smoke.sh`
- Modify: `deploy/tests/test_remote_deploy_scripts.py`

**Interfaces:**
- Consumes: previous healthy release path, inherited `.env`, inherited `compose.server-https.yaml`, inherited `deploy/nginx/production.conf.template`, and `AURORA_WEB_SMOKE_MARKER` from server `.env`.
- Produces: `shared-nginx-smoke.sh <aurora-web-container-id>`; exit `0` only when routing, website provenance, and container identity are healthy.

- [ ] **Step 1: Add failing source-contract and fake-command tests**

```python
def test_release_inherits_shared_nginx_before_compose_validation():
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    copy_index = source.index('production.conf.template')
    config_index = source.index('config --quiet')
    assert copy_index < config_index


def test_release_and_rollback_use_three_domain_smoke_without_orphan_cleanup():
    for path in (RELEASE_SCRIPT, ROLLBACK_SCRIPT):
        source = path.read_text(encoding="utf-8")
        assert "shared-nginx-smoke.sh" in source
        assert "--remove-orphans" not in source
```

Add a fake `docker` executable fixture that records invocations and returns stable IDs for `aurora-web` and the proxy. Assert a website marker failure exits non-zero and invokes `rollback_services` without an `aurora-web` Compose operation.

- [ ] **Step 2: Run the release-script tests and verify RED**

Run:

```powershell
python -m pytest deploy/tests/test_remote_deploy_scripts.py -q -p no:cacheprovider
```

Expected: failures mention missing template inheritance and missing shared smoke script.

- [ ] **Step 3: Implement shared-template inheritance and preflight**

Add this order to `remote-release.sh` before any candidate service starts:

```bash
cp "${previous_release}/deploy/.env" "${release_dir}/deploy/.env"
cp "${previous_release}/deploy/compose.server-https.yaml" "${release_dir}/deploy/compose.server-https.yaml"
cp "${previous_release}/deploy/nginx/production.conf.template" \
  "${release_dir}/deploy/nginx/production.conf.template"

python3 "${release_dir}/deploy/shared_nginx_release_validator.py" \
  --nginx-template "${release_dir}/deploy/nginx/production.conf.template"
compose_at "${release_dir}" config --quiet
```

Capture `aurora_web_before="$(docker inspect --format '{{.Id}}' aurora-web)"`, verify both containers contain `beyondcandidate_edge` in `.NetworkSettings.Networks`, and run candidate proxy `nginx -t` before switching `current`.

- [ ] **Step 4: Implement symmetric three-domain runtime smoke**

`shared-nginx-smoke.sh` must:

```bash
test "$(docker inspect --format '{{.Id}}' aurora-web)" = "$1"
docker inspect --format '{{json .NetworkSettings.Networks}}' aurora-web | grep -q 'beyondcandidate_edge'
curl --fail --silent --show-error https://hr.aurora-tek.cn/health/ready >/dev/null
curl --fail --silent --show-error https://hr.aurora-tek.cn/ >/dev/null
curl --fail --silent --show-error https://aurora-tek.cn/ | grep -Fq "$AURORA_WEB_SMOKE_MARKER"
curl --fail --silent --show-error https://www.aurora-tek.cn/ | grep -Fq "$AURORA_WEB_SMOKE_MARKER"
```

The script must reject an empty `AURORA_WEB_SMOKE_MARKER`, use bounded curl timeouts, and never echo response bodies. Call it after release health checks and after rollback health checks.

- [ ] **Step 5: Make rollback restore the previous shared config before smoke**

`remote-rollback.sh` must validate the target release's inherited Nginx template, run `compose_previous config --quiet`, start only the `beyondcandidate` project services, call shared smoke with the captured website ID, and update `current` only after all checks pass.

- [ ] **Step 6: Run focused release verification**

Run:

```powershell
python -m pytest deploy/tests/test_remote_deploy_scripts.py deploy/tests/test_shared_nginx_release_validator.py -q -p no:cacheprovider
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-release.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/remote-rollback.sh
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/shared-nginx-smoke.sh
```

Expected: all tests pass and all three shell syntax checks exit `0`.

- [ ] **Step 7: Commit release and rollback protection**

```powershell
git add deploy/remote-release.sh deploy/remote-rollback.sh deploy/shared-nginx-smoke.sh deploy/tests/test_remote_deploy_scripts.py
git commit -m "fix: preserve website routes during recruitment deploys"
```

---

### Task 3: Add The Protection To The Deployment Gate And Runbook

**Files:**
- Modify: `deploy/deploy-remote.ps1`
- Modify: `deploy/production-operations-runbook.md`
- Modify: `server/tests/test_production_topology.py`

**Interfaces:**
- Consumes: Task 1 validator and Task 2 smoke script.
- Produces: local validation gate that blocks upload before an unsafe release artifact can reach production.

- [ ] **Step 1: Write failing topology assertions**

```python
def test_remote_release_protection_is_part_of_repository_gate():
    script = (ROOT / "deploy" / "deploy-remote.ps1").read_text(encoding="utf-8")
    assert "test_shared_nginx_release_validator.py" in script
    assert "test_remote_deploy_scripts.py" in script
    assert "shared-nginx-smoke.sh" in script
```

- [ ] **Step 2: Run the topology test and verify RED**

Run:

```powershell
python -m pytest server/tests/test_production_topology.py -q -p no:cacheprovider
```

Expected: the new release-protection gate assertion fails.

- [ ] **Step 3: Wire exact pre-upload checks into `deploy-remote.ps1`**

Run these checks before archive creation or SSH upload:

```powershell
python -m pytest `
  deploy/tests/test_shared_nginx_release_validator.py `
  deploy/tests/test_remote_deploy_scripts.py `
  -q -p no:cacheprovider
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/shared-nginx-smoke.sh
```

Keep the existing external browser smoke and automatic rollback behavior unchanged after the remote release finishes.

- [ ] **Step 4: Document operator inputs and recovery evidence**

Update the canonical runbook with:

```text
Required server-only setting: AURORA_WEB_SMOKE_MARKER=<stable text from the website homepage>
Inherited artifacts: deploy/.env, deploy/compose.server-https.yaml,
deploy/nginx/production.conf.template
Required post-release evidence: three domain statuses, website marker match,
unchanged aurora-web container ID, nginx -t, and current release symlink.
```

State explicitly that a missing previous shared template is a release blocker, not permission to fall back to the repository template.

- [ ] **Step 5: Run the complete deployment-plan gate**

Run:

```powershell
python -m pytest deploy/tests/test_shared_nginx_release_validator.py deploy/tests/test_remote_deploy_scripts.py server/tests/test_production_topology.py server/tests/test_nginx_security.py -q -p no:cacheprovider
PowerShell -ExecutionPolicy Bypass -File deploy/deploy-remote.ps1 -ValidateOnly
git diff --check
```

Expected: pytest passes, validation exits before SSH mutation with a successful local gate, and `git diff --check` prints nothing.

- [ ] **Step 6: Commit the deployment gate and runbook**

```powershell
git add deploy/deploy-remote.ps1 deploy/production-operations-runbook.md server/tests/test_production_topology.py
git commit -m "docs: require shared-route deployment checks"
```
