# Production operations runbook

## Readiness status

This canonical operations runbook describes the Phase 6C operating contract.
It does not declare the service production ready. Launch still requires
provider-specific off-host storage, reviewed identities, production
preflight/provisioning integration after shared-file release,
provider-specific validation of the bundled S3-compatible atomic publisher,
the released real B2B3 CLI and B2B3 Worker, and a complete real restore drill.
The local disposable MinIO race proves process concurrency only; it is not an
off-host deployment. The traffic gate can verify signed, replay-resistant B2B3
evidence, but deliberately emits traffic-closed evidence and cannot open
production traffic. The production traffic decision remains external.

## Preflight and launch

### Current single-server release command

For the current SSH-managed trial server, run the checked-in PowerShell entrypoint from a clean
Windows worktree. It builds versioned images locally, transfers a source snapshot and image
archives over SSH, keeps the previous release directory as the rollback point, preserves the
server-owned `.env` and TLS overlay, uses the fixed `beyondcandidate` Compose project name, and
verifies container health plus the public HTTPS browser boundary before reporting success.

```powershell
PowerShell -ExecutionPolicy Bypass -File deploy\deploy-remote.ps1 `
  -RemoteHost root@120.79.184.221 `
  -Domain hr.aurora-tek.cn `
  -Scope all
```

For a frontend-only change that requires no backend image or migration:

```powershell
PowerShell -ExecutionPolicy Bypass -File deploy\deploy-remote.ps1 -Scope frontend
```

The command rejects a dirty worktree by default. `-AllowDirty` is reserved for an explicitly
approved emergency release and marks the release ID as dirty. `-SkipTests` is also an emergency
override, not the normal path. `-ValidateOnly` checks local prerequisites and release identity
without building or changing the server. It runs the shared Nginx release gate: the release
validator tests, remote deployment-script tests, and Git Bash syntax check for
`deploy/shared-nginx-smoke.sh`. This gate runs before any archive creation or SSH upload and
cannot be skipped by `-SkipTests`.

Before release, configure the required server-only setting
`AURORA_WEB_SMOKE_MARKER=<stable text from the website homepage>` in the protected deployment
environment. Do not put its production value in this repository. The release inherits the
server-owned `deploy/.env`, `deploy/compose.server-https.yaml`, and
`deploy/nginx/production.conf.template`. A missing previous shared template is a release
blocker, not permission to fall back to the repository template.

Retain post-release evidence for the three domain statuses, website marker match, unchanged
`aurora-web` container ID, `nginx -t`, and the current release symlink. A failed shared-route
smoke keeps the candidate from becoming current and uses the existing rollback path; inspect the
same evidence again before further traffic decisions.

This single-host archive transfer is the current operational path for the trial deployment. It
does not replace the immutable registry/digest and progressive rollout process required below
for a multi-host or formally production-ready launch.

Before any launch, verify approved DNS and TLS certificates, host and remote
storage capacity, clock synchronization, Docker/Compose versions, immutable
image digests, secret-file ownership, remote TLS, PostgreSQL/MinIO reachability,
and independent ledger/business destinations. Run the existing production
preflight unchanged, then run backup destination, manifest schema, and
the fixed `preflight-drill` plus disposable drill Compose checks from the
backup-recovery runbook. Preflight must reject an invalid latest restore point,
an unverified catalog, or any image not resolved as `image@sha256`.

Build and publish all release-owned images from the exact reviewed commit. Set
the three repositories to approved registry locations before running this
sequence. `TARGET_PLATFORM` must match the target Linux host.

```sh
export RELEASE_COMMIT=$(git rev-parse HEAD)
export TARGET_PLATFORM=linux/amd64
: "${APP_IMAGE:?Set the application image repository}"
: "${FRONTEND_IMAGE:?Set the frontend image repository}"
: "${BACKUP_IMAGE:?Set the backup image repository}"

docker buildx build --platform "$TARGET_PLATFORM" --target runtime \
  -f server/Dockerfile -t "$APP_IMAGE:$RELEASE_COMMIT" --push .
docker buildx build --platform "$TARGET_PLATFORM" \
  -f deploy/nginx/Dockerfile -t "$FRONTEND_IMAGE:$RELEASE_COMMIT" --push \
  docs/design/prototypes/ats-low-fi-option-2
docker buildx build --platform "$TARGET_PLATFORM" \
  -f deploy/backup/Dockerfile -t "$BACKUP_IMAGE:$RELEASE_COMMIT" --push \
  deploy/backup

export APP_IMAGE_DIGEST=$(docker buildx imagetools inspect \
  "$APP_IMAGE:$RELEASE_COMMIT" --format '{{.Manifest.Digest}}')
export FRONTEND_IMAGE_DIGEST=$(docker buildx imagetools inspect \
  "$FRONTEND_IMAGE:$RELEASE_COMMIT" --format '{{.Manifest.Digest}}')
export BACKUP_IMAGE_DIGEST=$(docker buildx imagetools inspect \
  "$BACKUP_IMAGE:$RELEASE_COMMIT" --format '{{.Manifest.Digest}}')
printf 'app=%s@%s\nfrontend=%s@%s\nbackup=%s@%s\n' \
  "$APP_IMAGE" "$APP_IMAGE_DIGEST" \
  "$FRONTEND_IMAGE" "$FRONTEND_IMAGE_DIGEST" \
  "$BACKUP_IMAGE" "$BACKUP_IMAGE_DIGEST"
```

Record those repositories and digests in the protected release environment
and evidence store. Do not use the example registry or all-zero digest from
`.env.example`. The release preflight parses the final merged Compose model and
fails if any production service has a mutable/malformed image or local build,
or if the proxy has a host static-asset override or the legacy on-host-only
backup is enabled.

On the target Linux host, with external traffic still closed, execute:

```sh
# The protected env file is authoritative for release image references. Remove
# build-shell leftovers so Compose cannot silently override it.
unset APP_IMAGE APP_IMAGE_DIGEST FRONTEND_IMAGE FRONTEND_IMAGE_DIGEST

COMPOSE_ENV_FILE=deploy/.env sh deploy/production-preflight.sh
COMPOSE_ENV_FILE=deploy/.env sh deploy/observability-preflight.sh
OBSERVABILITY_PREFLIGHT_MODE=production \
  COMPOSE_ENV_FILE=deploy/.env \
  sh deploy/observability-preflight.sh

docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml \
  pull
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml \
  up -d --no-build
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml ps
python3 deploy/release-runtime-validator.py --env-file deploy/.env

curl --fail --show-error "https://$SERVER_NAME/health/live"
curl --fail --show-error "https://$SERVER_NAME/health/ready"
```

From an operator workstation with the frontend package dependencies and
Chromium installed, run the read-only same-origin browser smoke. It enters no
credentials and verifies the real React login page, trusted TLS, readiness,
and that `/api/v1/me` returns unauthenticated JSON rather than SPA HTML.

```sh
cd docs/design/prototypes/ats-low-fi-option-2
npm ci
npx playwright install chromium
UX09_PRODUCTION_URL="https://$SERVER_NAME/" \
  node scripts/production-browser-smoke.cjs
```

Reliability objectives are a 24-hour RPO and 4-hour RTO. Schedule paired backup
every 12 hours to preserve RPO margin. Launch is blocked until the newest two
valid complete points are restorable and the latest ledger archive freshness is
proved. Backups only on the application host, PostgreSQL-only dumps, or a
traffic-open path are launch blockers. Caller JSON, mock output, unsigned or
replayed B2B3 evidence cannot change the foundation closed state.

Use a progressive rollout: deploy one compatible instance with traffic closed,
run one synthetic publisher canary with a new run ID, pass migrations/readiness
and a read-only smoke, then increase traffic in bounded steps while watching
user-facing HTTPS success, latency, queue age, storage errors, and restore-point
freshness. Resource metrics are supporting diagnostics, not the only alerts.

## Upgrade and migration

Create and validate an off-host pre-upgrade restore point and independent ledger
archive before changing production. Record application, PostgreSQL, MinIO,
backup-tool, schema-head, and manifest versions. Apply forward-only migrations;
never downgrade the database as rollback. Keep traffic bounded until error,
latency, queue, storage, and governance signals remain healthy.

After every forward migration, reconcile the application role against the new
schema before starting API or worker processes:

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T postgres sh /docker-entrypoint-initdb.d/10-provision-app-role.sh
```

Do not continue to readiness or traffic checks if this command fails. PostgreSQL
initialization scripts only run automatically when a new database volume is
created; they do not grant access to tables added by a later migration.

The application rollback path is the last compatible immutable application
image against the forward-migrated schema. Define that compatibility before
launch. If compatibility is not proved, stop rollout and recover forward rather
than improvising a database rollback.

## Rollback and abort criteria

Before every release, record the prior compatible image digest, traffic-shift
command, responsible operator, and abort threshold. Roll back application
traffic progressively when HTTPS readiness, error rate, latency, queue age, or
storage/reference checks breach the release budget. Keep migrations forward-only.

For suspected data corruption or host loss, close traffic and follow the
isolated/full-host recovery procedure. Restore into new volumes, restore ledger
first, run the real B2B3 recovery, and keep the foundation traffic gate closed.
Any future traffic-open implementation requires the separately released signed
B2B3 protocol and review. Never overwrite
production volumes in place and never use the disposable drill Compose project
as a production topology.

For an application-only rollback, first close or reduce external traffic and
restore `APP_IMAGE`, `APP_IMAGE_DIGEST`, `FRONTEND_IMAGE`, and
`FRONTEND_IMAGE_DIGEST` in the protected `deploy/.env` as one previously
recorded compatible release. Preserve the forward-migrated database, backup
leases, and `/var/lib/ux09-backup/pending-run.json`. Then run from a shell where
the protected file is authoritative:

```sh
unset APP_IMAGE APP_IMAGE_DIGEST FRONTEND_IMAGE FRONTEND_IMAGE_DIGEST
COMPOSE_ENV_FILE=deploy/.env sh deploy/production-preflight.sh
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml \
  config --images
# Stop unless the rendered application and frontend repository@digest values
# exactly match the recorded rollback release.
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml \
  pull proxy api worker queue-exporter
docker compose --env-file deploy/.env \
  -f deploy/compose.yaml \
  -f deploy/compose.production.yaml \
  -f deploy/compose.observability.yaml \
  up -d --no-build
python3 deploy/release-runtime-validator.py --env-file deploy/.env
curl --fail --show-error "https://$SERVER_NAME/health/live"
curl --fail --show-error "https://$SERVER_NAME/health/ready"
```

Run the read-only browser smoke again before any independent traffic decision.
If the previous application image is not proven compatible with the current
schema, do not downgrade the database or start that image; keep traffic closed
and recover forward. For integrity loss or host loss, use the isolated/full-host
ledger-first recovery procedure instead of this image rollback.

## Credential and signing-key rotation

Rotate one least-privilege identity at a time: create a new protected secret
file, verify append/read/delete behavior within its exact role, switch the
scheduler or temporary restore, observe one successful cycle, then revoke the
old identity. Business source, destination append, prune, restore, ledger
archive, and ledger restore credentials remain distinct.

Ledger signing-key rotation creates a new explicit key version, preserves the
verification history for all retained archives, marks exactly one version
active, verifies old and new signatures, then retires the old signing key.
Replacing one unversioned key is prohibited. Never record key material in the
history contract, manifests, logs, reports, or commits.

Paired backup uses a distinct read-only `LEDGER_MANIFEST_VERIFY_KEY_FILE` and a
fetched immutable `LEDGER_PAIRING_GROUP_PATH`. Rotation is incomplete until the
pairing verifier proves the manifest HMAC/key version, COMPLETE, archive hash
and size, archive run ID, and cutoff freshness with both retained and new keys.

## Monitoring, alerting, and evidence

Track valid-complete restore-point age, paired dump/snapshot completion,
reference mismatch count, ledger freshness and signed restore proofs, prune
failures, atomic publisher lease/receipt failures, destination write
failures, drill RPO/RTO, B2B3 gate status, and traffic-gate status. Alert on
user-impacting symptoms: no valid restore point by 18 hours, projected breach of
the 24-hour RPO, recovery unable to meet the 4-hour RTO, or traffic exposed
without completed B2B3 evidence. Route every alert to the canonical backup
recovery procedure.

Publisher exit 75 is a duplicate/lease conflict; alert if it occurs for a newly
allocated scheduler run ID. Exit 74 means provider upload or verification
failed before the COMPLETE commit phase. Exit 76 means commit status is unknown,
including an ambiguous COMPLETE PUT or any later COMPLETE stat/get or receipt
failure; page immediately and run the backup recovery runbook's read-only
reconciliation for the same run ID. No exit code alone proves COMPLETE absent.
Exit 78 is an input/security-contract rejection and blocks rollout. Keep alert
labels aggregate—never attach destination objects, source filenames, config
contents, credentials, or raw `mc` stderr.

Publisher rollback is operationally reversible: stop new backup launches and
restore the refusing rclone publication configuration while preserving all
remote leases and groups. Never delete a lease to force retry. Resolve every
commit-unknown run through read-only reconciliation before choosing any later
run ID. After status, root cause, and provider policy are reviewed, run one
canary before restoring the 12-hour schedule.

Evidence is aggregate and non-PII: versions/digests, timestamps, sizes, hashes,
counts, mismatches, retention decisions, and gates. It must not contain object
keys, candidate/request IDs, filenames, content, credentials, PII, or secret
values.

## Incident command and escalation

Treat failures as system failures. Assign incident command, operations,
database, storage, and governance/B2B3 owners; preserve failed-state evidence;
close traffic when integrity is uncertain; and stop destructive prune or
restore steps. Escalate on invalid latest backup, retention-policy mismatch,
ledger freshness/signature failure, reference mismatch, inability to prove
disposable isolation, B2B3 unavailability, or RPO/RTO risk.

After recovery, run a blameless review and convert repeated manual steps into
tested automation or this runbook. Do not weaken fail-closed gates to shorten an
incident.
