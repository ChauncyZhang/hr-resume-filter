# Phase 6C foundation report

## Status

This change is the Phase 6C foundation only. It is not production ready and
does not claim Phase 6C completion. The independent slice establishes a pinned
backup toolchain, paired restore-point state machine, off-host and secret-file
contracts, complete-group-only prune planning, ledger separation, disposable
restore guards, a default-closed traffic gate, canonical runbooks, and focused
contract tests.

A complete real restore drill still depends on the released real B2B3 CLI and
B2B3 Worker for prevalidation, recovery checkpoints, recovery generation,
re-deletion, idempotency, tamper failure, and checkpoint reclaim. This slice
exposes those command/evidence interfaces and refuses to open traffic when they
are absent; it does not implement or fake B2B3.

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
  zero reference mismatches precede manifest and COMPLETE publication.
- Off-host URI validation rejects local/application-host and PostgreSQL/MinIO
  data-volume paths. Credentials and signing material are distinct protected
  files and are absent from argv values, logs, manifests, and evidence.
- Prune is complete-group-only, fails closed on invalid latest or retention
  policy mismatch, and preserves at least the newest two valid points.
- The live ledger is excluded from business snapshots. Archive destination,
  credentials, lifecycle, manifest, restore identity, and signing-key
  version/history contracts are independent; business capabilities cannot
  restore/delete ledger data.
- Restore and drill reject production projects/volumes and require
  `DISPOSABLE_RECOVERY_CONFIRMED=1`. Ledger restore is ordered before an older
  business restore. Traffic remains closed until real B2B3 CLI and B2B3 Worker
  evidence passes every required gate.
- The operational contract schedules backup every 12 hours, budgets a 24-hour
  RPO and 4-hour RTO, and excludes object keys, candidate/request IDs,
  filenames, PII, content, credentials, and secrets from public evidence.

## TDD and verification evidence

The initial focused RED run produced `23 failed`: every failure was the intended
absence of the new Phase 6C contract surface. The generated-artifact guard then
failed on the observed `deploy/backup/__pycache__`/`.pyc`, and passed after
scoped cleanup plus bytecode suppression. A submission review added four
regressions that first failed for strict schema extensions, missing manifest
signature verification, cutoff-bounded ledger restore, and run-ID overwrite;
all four were fixed before final GREEN.

Fresh pre-commit evidence:

- Focused contract suite: `27 passed`.
- POSIX `sh -n` for all backup scripts: success.
- Isolated `docker compose ... config --quiet`: success; no traffic service or
  production volume is present.
- Digest-pinned image build: success, local image ID
  `sha256:5b90360b046c774af7081548b7453e164946f2a43b92a26fc177c1e8894e9084`.
- Runtime versions: Python 3.12.13, PostgreSQL dump/restore 16.9, MinIO Client
  `RELEASE.2025-07-21T05-28-08Z`, and rclone 1.70.3.
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
