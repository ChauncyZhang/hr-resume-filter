# Backup and recovery runbook

## Status and safety boundary

This is the canonical Phase 6C foundation runbook. It defines executable
contracts for paired PostgreSQL and business-object restore points, independent
ledger archives, pruning, isolated restore, and evidence. It is not production
ready until an off-host destination is provisioned, least-privilege identities
are verified, the released real B2B3 CLI and B2B3 Worker are connected, and a
complete real restore drill proves the 24-hour RPO and 4-hour RTO.

Never run restore or drill commands against the `ux09` Compose project or its
volumes. The guard requires `DISPOSABLE_RECOVERY_CONFIRMED=1`, a project named
`ux09-backup-drill-<unique>`, and volumes whose names begin with that exact
project name. The traffic gate defaults closed and cannot pass on Phase 6C
restore evidence alone.

## Architecture and trust boundaries

- `deploy/backup/Dockerfile` pins PostgreSQL 16.9, MinIO Client, and rclone by
  immutable tag and digest. Build and record the resulting local image digest.
- `backup.sh` creates one PostgreSQL custom-format dump and one business MinIO
  snapshot under the same `backup_run_id`. The live governance ledger bucket is
  rejected from the business bucket list.
- `ledger-archive.sh` uses separate source, append, restore, lifecycle, and
  signing-key-history contracts. The business read/append/prune identities must
  have no ledger restore or delete grants.
- The destination adapter stages a group, publishes data and manifest, then
  writes `COMPLETE` last. Consumers ignore every group without a valid marker.
- PostgreSQL passwords, MinIO aliases, destination credentials, and signing
  material are protected secret files. Never pass their values in argv, shell
  tracing, logs, manifests, reports, or tickets.

Production backups must use a destination URI whose host differs from the
application host and whose path is outside PostgreSQL and MinIO data volumes.
Local paths, `file:` URIs, application-host SSH paths, and data-volume paths
fail closed. The application host is not an acceptable off-host destination.

## Installation and prerequisites

1. Provision independent business-backup and ledger-archive failure domains.
   Configure storage-side encryption, versioning/object lock where approved,
   capacity monitoring, and lifecycle policies. Keep DNS and TLS verification
   enabled for remote endpoints.
2. Provision distinct identities for PostgreSQL backup read, business source
   read, business destination append, business prune deletion, business
   restore, ledger source read, ledger archive append, and ledger restore.
   Revoke retired identities after rotation and after temporary restores.
3. Create protected files for `PGPASSFILE`, each `*_CONFIG_FILE`, and signing
   keys. Restrict ownership to the backup runtime. Do not place them in this
   repository or in Compose environment values.
4. Build the toolchain:

   ```sh
   docker build --pull=false -t ux09-backup:phase6c-foundation deploy/backup
   docker image inspect ux09-backup:phase6c-foundation --format '{{.Id}}'
   ```

5. Verify PostgreSQL 16 compatibility, destination TLS/DNS, free staging
   capacity for a full dump plus object snapshot, and clock synchronization.
   Provisioning of production roles/policies remains outside this independent
   slice and requires the B2B shared-file release.

## Required secret-file and adapter contract

The coordinator invokes one executable path per client variable; shell command
strings are rejected. Client arguments contain only secret-file paths, safe
endpoint identifiers, run IDs, and local evidence paths.

- `BUSINESS_SNAPSHOT_CLIENT`: `snapshot --config-file FILE --buckets LIST
  --output PATH --inventory PATH`. Inventory entries contain only a keyed/path
  hash, content hash, and size; raw object keys and filenames are forbidden.
- `BACKUP_DESTINATION_CLIENT`: `stage-group`, `publish-group`, `abort-group`,
  `catalog`, `fetch-complete-group`, and `delete-complete-group`.
- `REFERENCE_VALIDATOR`: validates database object references against the
  captured inventory and emits only checked/mismatch counts.
- `LEDGER_ARCHIVE_CLIENT`: `snapshot`, `publish`, and `restore-latest`. Restore
  always selects the latest valid independent archive, never one bounded by the
  older business backup cutoff. Its credentials and destination are independent.
- `BUSINESS_RESTORE_CLIENT`: restores the verified snapshot with the temporary
  business restore identity; it has no access to the ledger archive.

`destination-rclone.sh` and `minio-business.sh` are baseline adapters in the
pinned image. Production enablement must verify provider-specific atomic marker
semantics, least-privilege policies, TLS, and lifecycle behavior.

## First paired backup

1. Run the independent ledger archive first. Its manifest must record the
   archive cutoff, entry count, archive hash, lifecycle policy version, and all
   ledger signing-key versions. The key history has exactly one active version
   and retained retired versions; replacing one unversioned key is forbidden.
2. Export a retention-policy snapshot from
   `retention_policies.backup_window_days` with its policy version. Supply that
   exact value as `BACKUP_WINDOW_DAYS`; no default is permitted.
3. Set a non-PII `BACKUP_RUN_ID`, UTC cutoff, pinned image digest, business
   buckets excluding the live ledger, protected secret-file paths, off-host
   destination, application hostname, and client executable paths.
4. Run `deploy/backup/backup.sh`. It must finish `pg_restore --list`, dump and
   snapshot hashes, complete object inventory, and zero reference mismatches
   before writing `manifest.json` and `COMPLETE`.
5. Fetch the published group with a read-only identity and rerun manifest,
   marker, hash, inventory, and `pg_restore --list` validation. Record only the
   non-PII evidence location and result.

Schedule ledger archive followed by paired backup at least every 12 hours. A
systemd timer should use `OnCalendar=*-*-* 00,12:00:00`,
`Persistent=true`, randomized delay, and an overlap-preventing lock. Alert on
the user-impacting symptom that no valid complete restore point has been
published within 18 hours; page before the 24-hour RPO is exhausted. Do not
infer freshness from process success or a dump file alone.

## Complete-group-only prune

Run `prune.sh` only after catalog validation. It fails closed when the latest
point is incomplete/invalid, any complete point disagrees with the current
`backup_window_days`, the catalog is malformed, or fewer than two valid points
exist. It ignores incomplete staging groups and deletes only an entire valid
complete group older than the policy cutoff while preserving the newest two
valid points. Ledger archives use their independent lifecycle and identity;
business prune credentials must be unable to list, restore, or delete them.

## Backup selection

Choose the newest complete point at or before the incident cutoff that passes
marker, schema, image/version compatibility, dump list, hashes, inventory, and
reference gates. Reject an invalid latest point and escalate; do not silently
fall back. Confirm its ledger archive is at least as fresh as the selected
business point. Record only run IDs, timestamps, aggregate counts, hashes, and
gate results—never object keys, candidate/request identifiers, filenames,
content, credentials, or PII.

## Isolated restore and recovery drill

Use a unique project and new volumes:

```sh
export BACKUP_DRILL_PROJECT=ux09-backup-drill-$(date -u +%Y%m%d%H%M%S)
export COMPOSE_PROJECT_NAME=$BACKUP_DRILL_PROJECT
export DISPOSABLE_RECOVERY_CONFIRMED=1
docker compose -f deploy/compose.backup-drill.yaml config --quiet
docker compose -f deploy/compose.backup-drill.yaml up -d postgres minio backup-tool
```

The drill sequence is strict:

1. Seed synthetic candidate/application/resume/feedback rows and business
   objects, create and validate one paired restore point, then add post-cutoff
   canaries.
2. Complete a real B2B2 deletion and independently preserve its ledger.
3. Start RTO timing. Restore the latest valid ledger archive first; never roll
   back the ledger. Then restore PostgreSQL and business objects into the new
   disposable volumes.
4. Verify Alembic head, database permissions, aggregate row/object counts,
   hashes, and references. Recovery evidence still records `traffic_open=false`.
5. Set `B2B3_CLI_COMMAND` and `B2B3_WORKER_COMMAND` only to the released real
   implementations. Run them to prevalidate, checkpoint, advance recovery
   generation, re-delete restored PII, and process Worker jobs. This foundation
   intentionally does not implement or fake either interface.
6. Require B2B3 evidence for tombstones, absent objects, safe audit counts,
   generation, repeat idempotency, tamper failure, and checkpoint reclaim.
7. Start API/Worker/proxy only after `traffic-gate.sh` accepts both restore and
   B2B3 evidence. Pass HTTPS readiness and read-only smoke, stop RTO timing, and
   prove `failure_at - backup_cutoff <= 24 hours` and total RTO `<= 4 hours`.

Until step 7 completes, do not publish ports, remove the traffic-closed marker,
or route production traffic. `drill.sh` deliberately fails closed while the
real B2B3 integration is unavailable.

## Full-host recovery

Rebuild the host from approved immutable artifacts, restore networking/TLS/DNS,
mount only new empty data volumes, and deploy the pinned compatible application
version with traffic disabled. Restore ledger first, then the selected paired
group, run all isolated verification and B2B3 gates, and only then authorize a
progressive traffic rollout. Abort on any identity overlap, marker/hash/schema
failure, reference mismatch, permission drift, RPO/RTO breach, or B2B3 gap.

## Evidence and escalation

Retain signed manifests, COMPLETE hashes, tool versions/digests, run/cutoff
times, sizes, aggregate object counts, reference mismatch count, ledger
freshness, prune decisions, measured RPO/RTO, B2B3 safe counts, and every gate
in the independent evidence destination. If validation fails, preserve the
incomplete group for forensic review without marking it complete, keep traffic
closed, stop prune, and escalate to the incident commander, database owner,
storage owner, and governance/B2B3 owner. Never paste secret files or raw data
into incident channels.

After a drill, use `docker compose -p "$BACKUP_DRILL_PROJECT" -f
deploy/compose.backup-drill.yaml down -v` only after confirming the project name
again. Production project or volume deletion is never an accepted recovery
step.
