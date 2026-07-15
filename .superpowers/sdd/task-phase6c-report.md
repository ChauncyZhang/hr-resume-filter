# Phase 6C foundation report

## Status

This change is the Phase 6C foundation only. It is not production ready and
does not claim Phase 6C completion. The independent slice establishes a pinned
backup toolchain, paired restore-point state machine, off-host and secret-file
contracts, complete-group-only prune planning, ledger separation, disposable
restore guards, a permanently disabled foundation traffic gate, canonical
runbooks, and focused contract tests.

A complete real restore drill still depends on the released real B2B3 CLI and
B2B3 Worker for prevalidation, recovery checkpoints, recovery generation,
re-deletion, idempotency, tamper failure, and checkpoint reclaim. This slice
documents the future command/evidence integration boundary but refuses every
traffic-open request, including caller JSON, mock, unsigned, missing-run, and
replayed evidence. It does not implement or fake B2B3.

## Scope and protected files

Only new files under `deploy/backup/**`, the isolated
`deploy/compose.backup-drill.yaml`, two canonical runbooks, one backup contract
test, and this report are owned. Base/production/observability Compose,
`deploy/.env.example`, provisioning, production preflight, server README,
migrations, application/worker/frontend code, and user protection files remain
unchanged and unstaged.

## Foundation contracts delivered

- PostgreSQL custom-format dump and business MinIO snapshot share one
  `backup_run_id`; `pg_restore --list`, hashes, hashed object inventory, and
  a bundled/pinned exact-count reference proof precede manifest and COMPLETE
  publication. Explicit trusted zero references are supported.
- Off-host URI validation rejects local/application-host and PostgreSQL/MinIO
  data-volume paths, unsafe URI syntax, and dangerous schemes. Run/generation
  fragments are validated before safe resolved joins. Credentials and signing
  material are distinct no-follow, single-inode protected files copied to
  process-private 0600 paths and absent from argv values, logs, manifests, and
  evidence. Child environments are strict allowlists rather than inherited
  process environments. Staging roots reject symlinks, Windows junctions, and
  reparse points; business bucket traversal/URI values are rejected before any
  client call.
- COMPLETE-last publication now requires an external conditional-create/lease
  publisher and a run/hash-bound receipt. The rclone adapter refuses publishing
  with safety code 78. The local concurrency reference proves one winner cannot
  be overwritten by the loser.
- Prune verifies canonical manifest schema/HMAC, COMPLETE, payload hashes,
  inventory, and custom dump list; it orders by COMPLETE metadata, fails closed
  on any invalid catalog/latest or retention mismatch, and preserves at least
  the newest two valid points.
- The live ledger is excluded from business snapshots. Archive destination,
  credentials, lifecycle, manifest, restore identity, and signing-key
  version/history contracts are independent; business capabilities cannot
  restore/delete ledger data. Restore verifies ledger schema, active key
  version/history, HMAC, COMPLETE, archive hash, freshness, run binding, and a
  signed run/generation-bound restore proof; client exit zero is insufficient.
  Backup pairing now uses the same strict archive-group validator through a
  dedicated `LEDGER_MANIFEST_VERIFY_KEY_FILE` and
  `LEDGER_PAIRING_GROUP_PATH`; bare/forged manifests or missing archive payloads
  cannot produce a paired manifest or COMPLETE.
- Restore and drill reject production projects/volumes and require
  `DISPOSABLE_RECOVERY_CONFIRMED=1`. Restore start atomically clears stale open
  state and binds closed evidence to the current run/generation. MinIO tar
  members are fully allowlisted before safe extraction. Traffic-open is not an
  available state transition in this foundation, even if JSON claims B2B3
  success.
- Drill has a fixed `preflight-drill` entry that validates a strict image
  repository/tag plus exact lowercase sha256 digest, disposable isolation, the
  verified catalog, retention policy, and invalid latest state before Compose.
- The operational contract schedules backup every 12 hours, budgets a 24-hour
  RPO and 4-hour RTO, and excludes object keys, candidate/request IDs,
  filenames, PII, content, credentials, and secrets from public evidence.

## TDD and verification evidence

The independent-review malicious reproductions were added before implementation.
The first expanded RED run produced `34 failed, 22 passed, 1 skipped`; after the
security helper layer, six orchestration/configuration tests remained RED. They
covered the disabled traffic transition, path traversal/symlink escape, lease
publication race, signed prune catalog, ledger proof binding, secret-file
TOCTOU, strict reference counts, immutable Compose image, and malicious tar
members. All non-platform-specific cases are GREEN. Generated-artifact checks
explicitly reject `deploy/backup/__pycache__`, `.pyc`, and `.pyo` files.

This review round added the remaining malicious reproductions first. The RED
run was `20 failed, 68 passed, 2 skipped`; after core GREEN, copyable drill
preflight/Compose/runbook assertions were separately observed RED before their
implementation. The Windows junction reproduction created a real junction and
passed after the root-boundary fix; no Windows capability was fabricated.

Fresh pre-commit evidence:

- Focused contract suite: `88 passed, 2 skipped` (two optional Windows symlink
  creation cases skipped; the non-privileged Windows junction/reparse test ran
  and passed, as did traversal, hardlink, absolute-path, bucket, env, and tar attacks).
- POSIX `sh -n` for all backup scripts: success.
- Isolated `docker compose ... config --quiet`: success; no traffic service or
  production volume is present.
- Fixed drill preflight: valid immutable image/catalog passed with traffic
  closed; malformed/invalid latest catalog failed closed as expected.
- Drill Compose requires `${BACKUP_IMAGE:?}@${BACKUP_IMAGE_DIGEST:?}` and has no
  mutable backup-tool tag or local build fallback.
- Python syntax, runtime secret scan, PII/secret-value scan, and generated
  artifact scan: success.

No real PostgreSQL/MinIO recovery drill is claimed: production-style protected
secret files, reviewed identities/destinations, and the real B2B3 integration
are intentionally absent from this independent foundation slice. Final staged
allowlist, diff check, and commit hash are recorded in the handoff.

## Remaining production integration

- Provision and policy-test production least-privilege identities and truly
  off-host business/ledger destinations after shared-file ownership releases.
- Integrate the 12-hour scheduler, production preflight, provisioning, and
  restore-point freshness alerts without modifying protected shared files in
  this slice.
- Validate provider-specific COMPLETE-last publication, object lifecycle,
  encryption, signing, credential rotation/revocation, and capacity behavior.
- Connect the real B2B3 CLI and Worker, seed the prescribed synthetic scenario,
  run a timed full restore into disposable volumes, then prove HTTPS readiness
  and read-only smoke before any traffic-open authorization.
- Capture measured RPO/RTO and all non-PII gate evidence. Until that complete
  real restore drill passes, Phase 6C and production readiness remain open.
