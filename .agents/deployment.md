# Enterprise Deployment

Deployment is an explicit production action. Do not deploy merely because code was edited or tests passed; the user must request deployment.

## Current target

- Internal repository: the repository containing this `.agents` directory.
- HR domain: `hr.aurora-tek.cn`
- Shared website domains: `aurora-tek.cn` and `www.aurora-tek.cn`
- Remote application root: `/opt/beyondcandidate`
- Active release link: `/opt/beyondcandidate/current`
- Versioned releases: `/opt/beyondcandidate/releases/<release-id>`
- Shared website container: `aurora-web`

Non-secret target values are in `deploy/target.psd1`. Secrets remain on the server or in a Git-ignored local target file. Never print or commit secret values.

## Normal release

Run from the private repository `main` branch with a clean private worktree and clean `product` submodule:

```powershell
.\验证代码.ps1
.\部署到生产.ps1 -ValidateOnly
.\部署到生产.ps1
```

Use a frontend-only release only when there is no backend, dependency, worker, migration, or server-contract change:

```powershell
.\部署到生产.ps1 -Scope frontend
```

Do not use `-SkipTests` or dirty-release overrides in the normal path.

## What the release script does

1. Resolves the private commit and pinned public product commit.
2. Runs the shared Nginx release gate.
3. Installs locked frontend dependencies and runs required tests unless explicitly overridden.
4. Builds versioned frontend and backend images locally.
5. Creates a product source archive and overlays reviewed private release scripts.
6. Uploads archives through SSH to a unique staging directory.
7. Starts required infrastructure, runs forward migrations, reconciles application database grants, and starts API, worker, and proxy.
8. Verifies container health, Nginx syntax, shared Docker networks, HR HTTPS, and both website domains.
9. Writes rollback metadata before atomically switching `/opt/beyondcandidate/current`.
10. Runs a browser smoke test and requests rollback if the final boundary fails.

The release must preserve `aurora-web`. It may connect that container to the shared network, but must not delete, rebuild, stop, or replace it. Shared Nginx validation requires the HR route and both website routes to remain present.

## First deployment to a replacement machine

External prerequisites:

1. DNS points the three approved domains to the new server.
2. The cloud firewall allows TCP 443.
3. SSH key authentication works for the configured administrator.
4. The valid TLS certificate and private key are available as separate local files.
5. The `aurora-web` website container is already running on the new server.

Create a local, ignored target file based on `deploy/target.psd1` and fill only the machine-specific certificate paths:

```powershell
Copy-Item deploy\target.psd1 deploy\target.local.psd1
.\部署到生产.ps1 -ConfigPath .\deploy\target.local.psd1
```

On an apt-based Linux server, bootstrap installs Docker and Compose when missing, generates cryptographically random production credentials, uploads TLS materials with restricted permissions, creates the initial Aurora system administrator, and then enters the normal versioned release path. The initial password is displayed once and must be changed after first login.

## Release acceptance

Do not report success until all of these are verified:

- `https://hr.aurora-tek.cn/health/ready` returns HTTP 200.
- `https://hr.aurora-tek.cn/` loads the real application.
- `https://aurora-tek.cn/` and `https://www.aurora-tek.cn/` load the website and contain the expected stable marker.
- API, worker, and proxy containers are healthy.
- `aurora-web` retains the same container ID.
- `/opt/beyondcandidate/current` points to the new release.
- The production browser smoke passes.

## Failure and cleanup rules

- Preserve the current release and its previous rollback target.
- Never delete persistent PostgreSQL, MinIO, backup, or governance volumes during release cleanup.
- Remove staging or release directories only after proving they are not current, not the rollback target, and not referenced by any container.
- If migrations make the previous application incompatible, recover forward instead of downgrading the database.
- Use `deploy/production-operations-runbook.md` for deeper rollback, recovery, backup, and incident procedures, but verify paths because older sections may describe the pre-split repository layout.
