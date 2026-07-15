# Production operations runbook

## Readiness status

This canonical operations runbook describes the Phase 6C foundation operating
contract. It does not declare Phase 6C or the service production ready. Launch
still requires provider-specific off-host storage, reviewed identities,
production preflight/provisioning integration after shared-file release, the
real B2B3 CLI and B2B3 Worker, and a complete real restore drill.

## Preflight and launch

Before any launch, verify approved DNS and TLS certificates, host and remote
storage capacity, clock synchronization, Docker/Compose versions, immutable
image digests, secret-file ownership, remote TLS, PostgreSQL/MinIO reachability,
and independent ledger/business destinations. Run the existing production
preflight unchanged, then run backup destination, manifest schema, and
disposable drill Compose checks from the backup-recovery runbook.

Reliability objectives are a 24-hour RPO and 4-hour RTO. Schedule paired backup
every 12 hours to preserve RPO margin. Launch is blocked until the newest two
valid complete points are restorable and the latest ledger archive freshness is
proved. Backups only on the application host, PostgreSQL-only dumps, or a
traffic gate without B2B3 evidence are launch blockers.

Use a progressive rollout: deploy one compatible instance with traffic closed,
pass migrations/readiness and a read-only smoke, then increase traffic in
bounded steps while watching user-facing HTTPS success, latency, queue age,
storage errors, and restore-point freshness. Resource metrics are supporting
diagnostics, not the only alerts.

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
first, run the real B2B3 recovery, and require the traffic gate. Never overwrite
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

## Monitoring, alerting, and evidence

Track valid-complete restore-point age, paired dump/snapshot completion,
reference mismatch count, ledger freshness, prune failures, destination write
failures, drill RPO/RTO, B2B3 gate status, and traffic-gate status. Alert on
user-impacting symptoms: no valid restore point by 18 hours, projected breach of
the 24-hour RPO, recovery unable to meet the 4-hour RTO, or traffic exposed
without completed B2B3 evidence. Route every alert to the canonical backup
recovery procedure.

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
