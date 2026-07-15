# Task B2B3 Report — Retention sweep and restore recovery

## Status

**DONE_WITH_CONCERNS**

Implementation commit: `f825bf057c9d6c78f1387dccca6bf36208f1c298`

B2B3 is implemented and verified with disposable PostgreSQL 16.9 and MinIO. The remaining
concern is operational evidence, not a known code failure: the complete B2B2-to-restore drill was
run with real services but root MinIO credentials, while the final refreshed CLI/worker run used
the provisioned delete-only and ledger-only identities against a re-signed copy of that real v2
ledger. A production backup provider, production credentials, and production traffic were not
used.

## Delivered behavior

- New deletions write canonical signed schema-v2 ledgers. V1 remains readable for frozen B2B2
  completion/redelivery and is rejected as recovery evidence.
- V2 requires exact fields, canonical private manifest/hash/counts, bounded collections and
  strings, canonical unique artifact descriptors, known kinds, exact configured bucket/prefix
  locations, and a valid HMAC. Discovery scans the bounded ledger prefix and rejects unknown
  versions, non-canonical paths, malformed/tampered/conflicting evidence, or applicable v1 before
  any durable recovery mutation.
- Daily retention sweep uses an exact tenant/date payload, a bounded `FOR UPDATE SKIP LOCKED`
  claim, due-date recomputation under lock, active-application/legal-hold/open-request exclusions,
  current private manifests, request-only creation, stable daily dedupe, and next-day scheduling.
  Initial jobs require the explicit release CLI; Alembic has no scheduling side effect.
- Restore recovery has no HTTP/OpenAPI route. The strict CLI validates separate application and
  governance PostgreSQL identities, scoped delete/ledger storage listing, all ledger evidence, and
  restored organization/candidate state before creating runs, checkpoints, or jobs.
- Recovery reconstructs only minimum non-PII request/artifact evidence, re-reads the exact ledger
  checksum per checkpoint, deletes only signed objects, invokes the frozen B2B1 redaction
  function, increments generation once, and safely resumes after lease reclaim. Empty restores
  retain a completed marker so restore-ID idempotency/conflict semantics still hold.
- Queue payload policies, terminal callbacks, worker handlers, settings, Compose environment,
  additive revision-0017 checkpoint persistence, README operations, and OpenAPI absence tests are
  wired.

## Security and migration notes

- Ordinary application DML and privileged redaction remain separate connections. The governance
  login retains no table/sequence privileges and only inherits the frozen executor function.
- Delete-only and ledger-only MinIO credentials remain distinct. The CLI's read-only prefix probes
  fail invalid identities/prefix policies before database mutation; the real worker run separately
  proved `DeleteObject` under the provisioned policy.
- Revision 0017 is additive for recovery checkpoints and relaxes `requested_by` only when
  `recovery_generation > 0`; normal approval/request constraints remain unchanged. Downgrade
  evidence locking includes the new table.
- No candidate, request, object, or ledger identifiers are emitted in recovery counters/errors.

## Verification

- Fresh image build: `docker build --target test -t ux09-b2b3-test -f server/Dockerfile .` — passed.
- Fresh-image B2B3 tests: `python -m pytest server/tests/test_governance_recovery.py server/tests/test_governance_retention_worker.py -q` — `30 passed in 12.71s`.
- Final recovery test after real SDK preflight correction: `24 passed in 19.57s`.
- Governance focused regression split (recovery, retention, frozen deletion worker, MinIO unit,
  deletion API/models, settings, worker): `179 passed, 4 skipped in 155.77s`.
- Host topology split: `python -m pytest server/tests/test_production_topology.py server/tests/test_observability_topology.py -q` — `15 passed in 16.85s`.
- `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet` — passed.
- `python -m compileall -q server/app server/migrations/versions` in the fresh image — passed.
- PostgreSQL migration suite first rerun: `10 passed, 1 skipped, 1 failed`; the failure was caused
  by the prior drill's temporary executor membership on `postgres`. After revoking that disposable
  membership, the failed privileged-boundary test passed (`1 passed in 11.13s`).
- Final clean-role migration suite in the fresh image: `11 passed, 1 skipped in 181.33s`.
- Scope check: `git diff --check` on B2B3-owned files — passed.

The intentionally over-broad local command that also included another agent's concurrent
`test_backup_restore_contract.py` produced `291 passed, 5 skipped, 3 failed`; those three tests
require host `git`/`docker` or symlink behavior unavailable in the bind-mounted test container.
They are not B2B3 failures and their files are excluded from this commit.

## Real recovery and retention evidence

- Full disposable drill: created synthetic PostgreSQL rows and resume/export objects, saved a
  `pg_dump` restore point, ran real B2B2 deletion, verified tombstone/object absence/v2 ledger,
  restored into a newly created database while preserving the ledger bucket, ran the real CLI and
  worker, and verified re-deletion and generation 1.
- Tampered ledger failed with `ledger_signature_invalid` and unchanged run/checkpoint/job counts.
  Same restore was a no-op; conflicting timestamp failed with unchanged counts.
- A claimed job was interrupted after lease claim; lease expiry/reclaim completed the durable
  checkpoint idempotently.
- Measured recovery execution RTO: `16.041s`. Measured restore-point exposure/RPO gap:
  `29912.456s` (about 8h18m32s) for this synthetic drill.
- Two concurrent real PostgreSQL retention handlers created exactly one request and one next-day
  job; a deliberately stale due fact created no request and was repaired/skipped.
- Final refreshed least-privilege run used repository provision scripts for separate app,
  governance, delete-only, and ledger-only identities. Current CLI returned `recovery_prepared=1`;
  the current worker reached `completed:completed`, tombstone/generation verification returned
  `1:1`; same restore returned 0; conflicting timestamp exited 2 with counts unchanged at `1:1:1`.

## Remaining real-environment gates

- Run the same end-to-end drill against the selected production backup/restore mechanism and its
  real RPO policy; the measured synthetic 8h18m32s restore gap is evidence, not an SLA pass.
- Run one uninterrupted drill where B2B2 and final B2B3 both use the production-equivalent
  least-privilege identities without re-signing/copying ledger evidence between phases.
- Validate alert routing/operator access and recovery timing under production data volume. The
  configured discovery ceiling is 10,000 ledgers by default and must be sized to the restore
  window before release.

## Scope protection

The commit excludes `.superpowers/sdd/task-1-report.md`,
`.superpowers/sdd/task-2-report.md`, `app/sample/candidates.csv`, and all other concurrent-agent
backup/e2e changes.
