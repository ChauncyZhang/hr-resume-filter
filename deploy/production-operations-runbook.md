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

Before any launch, verify approved DNS and TLS certificates, host and remote
storage capacity, clock synchronization, Docker/Compose versions, immutable
image digests, secret-file ownership, remote TLS, PostgreSQL/MinIO reachability,
and independent ledger/business destinations. Run the existing production
preflight unchanged, then run backup destination, manifest schema, and
the fixed `preflight-drill` plus disposable drill Compose checks from the
backup-recovery runbook. Preflight must reject an invalid latest restore point,
an unverified catalog, or any image not resolved as `image@sha256`.

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
