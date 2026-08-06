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

When the user explicitly asks to deploy, run exactly this from the private repository root:

```powershell
.\部署到生产.ps1
```

Do not mechanically run `验证代码.ps1`, `-ValidateOnly`, and the real deployment in sequence. Product validation belongs to development and release-candidate preparation; deployment does not repeat the full product suite by default. The entrypoint requires clean commits published at both repositories' `origin/main`, detects whether this is a first-machine bootstrap, and compares the active product commit to select `frontend` or `all` automatically.

Only override automatic scope when diagnosing the release mechanism:

```powershell
.\部署到生产.ps1 -Scope frontend
.\部署到生产.ps1 -Scope all
```

Use `-RunFullTests` only when the user explicitly asks to repeat the complete product suite during deployment or when existing validation evidence is not trustworthy:

```powershell
.\部署到生产.ps1 -RunFullTests
```

`-ValidateOnly` is for changes to deployment scripts and route protection. It is not a required step before every normal deployment. Do not use dirty-release overrides in the normal path.

## Nginx lifecycle

TLS files and the shared production Nginx template are configured once during first-machine bootstrap. A normal release does not ask the operator to configure Nginx again and does not replace the server-owned template.

Every release still performs a short route safety check because the application proxy container is versioned and replaced. The check copies the already active server-owned template into the candidate release, runs parser and shell tests, executes `nginx -t`, verifies the HR domain and both website domains, and confirms that `aurora-web` retained its container ID. This is validation of the existing configuration, not repeated configuration work. Do not tell the user that Nginx needs to be configured unless bootstrap prerequisites are genuinely missing or the inherited configuration fails validation.

## What the release script does

1. Resolves the private commit and pinned public product commit.
2. Runs the short shared-route safety gate without changing the active Nginx configuration.
3. Installs locked frontend dependencies; full product tests run only with `-RunFullTests`.
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

After bootstrap succeeds, future deployments use the normal one-command path. Do not upload certificates or edit Nginx again during ordinary application releases.

## Agent decision table

| Situation | Required action |
| --- | --- |
| User says only "deploy" | Run `部署到生产.ps1` from the private repository root. |
| Pure frontend product diff | Let `-Scope auto` select `frontend`; do not force `all`. |
| Backend, worker, dependency, migration, or mixed diff | Let `-Scope auto` select `all`. |
| Deployment scripts were edited | Run focused deployment tests and optionally `-ValidateOnly`, then the root entrypoint after authorization. |
| First deployment or replacement machine | Prepare DNS, 443, TLS files, SSH, and `aurora-web`; let the root entrypoint invoke bootstrap. |
| Existing production server | Never rerun bootstrap or manually change Nginx/TLS. |
| Full tests already passed during development | Do not repeat them during deployment. |
| Validation is missing or suspect | Run `验证代码.ps1` before deployment, or explicitly deploy with `-RunFullTests`. |

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
