# Phase 6C publisher slice report

## Status and scope

The independent S3-compatible publisher slice is implemented and locally
verified. It does not claim Phase 6C completion, production readiness, a real
off-host destination, or a restore drill. The real provider gate remains open.

The change is limited to `deploy/backup/**`, the backup contract test, the two
canonical operations runbooks, and this report. Governance/B2B3, migrations,
Compose, production preflight, provisioning, frontend, and protected user files
were not modified or staged.

## Delivered contract

- `s3-atomic-publisher.py` implements the existing
  `publish-complete-group --lease-config-file ...` interface for allowlisted
  `s3://` and `minio://` destinations using the already pinned `mc` binary.
- It validates all arguments and exact business/ledger source member sets
  before a client call. Run IDs, destination syntax, COMPLETE binding,
  manifest/run binding, source files, config link count, config mode, symlinks,
  junctions/reparse points, and receipt paths fail closed.
- Config files are opened with no-follow/inode checks. On POSIX, every source
  path component is pinned with `O_DIRECTORY|O_NOFOLLOW`, each exact member is
  opened relative to that fixed directory FD, and one read pass copies it into
  a process-private snapshot while computing size and SHA-256. Only that
  snapshot is validated and uploaded. Child environment inheritance is
  reduced; provider stdout/stderr is captured and never emitted.
- One random lease is written with provider-native `If-None-Match:*` under the
  fixed bucket-private lease prefix. There is no list-then-write lease path.
  The lease is never deleted. Existing lease/complete groups exit 75.
- Payload members are uploaded and independently size/SHA-256 verified by
  stat plus private download. COMPLETE is uploaded and verified last. Any
  ambiguous COMPLETE PUT or subsequent COMPLETE stat/get/receipt failure exits
  76 with commit status unknown; no exit code is used to infer COMPLETE absence.
- The local receipt has exactly the foundation schema and binds the run ID,
  COMPLETE SHA-256, committed state, and SHA-256 of the unlogged random lease.
  Receipt creation pins and validates the parent directory, uses no-replace
  `openat(O_CREAT|O_EXCL)`, fsyncs the file, then fsyncs the parent. Safety
  rejection is 78, pre-commit provider/verification failure is 74, and
  commit-unknown is 76; all output is generic and contains no destination
  object, source filename, config, client stderr, credential, or lease value.

## TDD evidence

- Initial publisher tests before implementation:
  `python -m pytest server/tests/test_backup_restore_contract.py -k "s3_publisher and not real_disposable" -q`
  -> `10 failed, 91 deselected`; every failure was the expected missing
  publisher surface.
- Contract GREEN after the first implementation: `7 passed, 3 skipped`.
  Windows skipped POSIX mode/symlink capabilities; the Linux image and real
  race exercised the protected config path.
- Image inclusion test was observed RED (`1 failed`) before changing the
  Dockerfile COPY allowlist, then GREEN (`1 passed`).
- The in-memory lease/subprocess regression was observed RED (`1 failed`) and
  then GREEN (`1 passed`).
- Fixed `mc --json` stdout error classification was observed RED (`3 failed`)
  and then GREEN (`3 passed`).

## Real disposable MinIO race

The gate used the pinned publisher image and a newly created local Docker
network, disposable MinIO container, and publisher runner. Publisher/`mc`
client credentials did not enter publisher/`mc` argv or child environment;
the client read its protected config file. The disposable MinIO server's
random credentials were injected into that server container by a protected
env-file. Two independent `docker exec` publisher processes raced the same run
ID.

Command:

```powershell
$env:UX09_RUN_MINIO_PUBLISHER_TEST='1'
$env:UX09_BACKUP_PUBLISHER_IMAGE='ux09-backup:phase6c-publisher-fix-test'
python -m pytest server/tests/test_backup_restore_contract.py::test_s3_publisher_real_disposable_minio_two_process_race -q
```

Final review-fix result: `1 passed in 17.39s` with no warning. Exactly one
process returned 0 and one returned 75. One permanent lease remained, the
immutable final group contained exactly the expected members, the winner
payload was preserved, exactly one strict bound receipt existed, and COMPLETE
metadata was not earlier than any payload. The receipt passed
`validate_publish_receipt`; the downloaded permanent lease matched its
`lease_id_hash`; read-only reconciliation produced the same receipt without
changing the remote key set. The same Linux gate also rejected a 0640 config,
config symlink, config hardlink, and source-directory symlink with exit 78
before provider mutation.

This is a same-machine disposable MinIO concurrency proof. It is explicitly
not off-host storage evidence and does not satisfy the production provider gate.

## Readiness, rollback, and observability

The publisher adapter is ready for provider-specific integration, not launch.
Restore-point freshness remains the user-impacting SLI: page when no valid
complete point exists by 18 hours and before the 24-hour RPO is exhausted.
Track aggregate exit 75 conflicts, exit 74 pre-commit provider/verification
failures, exit 76 commit-unknown outcomes, exit 78 safety rejections, receipt
failures, and completed restore-point age without high-cardinality
object/source labels.

Rollback is defined before rollout: stop new launches and restore the refusing
rclone publisher configuration. Preserve leases and groups; never delete a
lease to force retry. Reconcile every commit-unknown run read-only under its
original run ID before any later run is considered. After status and root cause
are resolved, run one canary before restoring the 12-hour schedule.

## Remaining external gates

- Provision a genuinely off-host S3-compatible endpoint and separately scoped
  append identity; prove conditional create with two hosts/processes there.
- Verify provider TLS/DNS, encryption, versioning/object lock policy where
  approved, lifecycle, capacity, checksum/download semantics, throttling, and
  credential rotation/revocation.
- Integrate production preflight, provisioning, scheduler, and alerting only
  after their shared-file ownership is released.
- Complete the real B2B3 CLI/Worker integration and timed isolated full restore
  drill, then prove RPO <= 24 hours, RTO <= 4 hours, HTTPS readiness, and
  read-only smoke before any traffic-open decision.

## Final fresh verification

- Full focused suite including disposable MinIO:
  `$env:UX09_RUN_MINIO_PUBLISHER_TEST='1'; $env:UX09_BACKUP_PUBLISHER_IMAGE='ux09-backup:phase6c-publisher-fix-test'; python -m pytest server/tests/test_backup_restore_contract.py -q`
  -> `106 passed, 10 skipped in 26.04s`. Remaining skips are pre-existing or
  unavailable Windows-only capability cases. The Linux publisher-only suite
  separately produced `25 passed, 91 deselected in 10.52s` with no skips.
- `docker build --pull=false -t ux09-backup:phase6c-publisher-fix-test deploy/backup`
  -> success; final local test image ID
  `sha256:963ceb09d5bc6ef3bf535b25c4c3a04917f193b1209fa56d6c8ece0d87e76d0f`.
- Git Bash `bash -n` for every `deploy/backup/*.sh`, in-memory Python compile
  for the publisher/test, and image executable check -> success.
- Generated `__pycache__`/`.pyc`/`.pyo` scan and sensitive-value scan -> clean.
- Scoped `git diff --check` -> success with no output. Final staged allowlist
  and commit are recorded in the handoff.

## Review remediation for a565d16

The review fixes retain the original publisher slice and do not change
governance/B2B3, migration, Compose, preflight, provisioning, or frontend
surfaces.

- RED: commit-unknown/reconciliation tests first produced `5 failed, 1 skipped,
  110 deselected`; POSIX source/receipt race tests first produced `5 failed,
  111 deselected` in the Linux test image.
- GREEN: commit-unknown/reconciliation produced `5 passed, 1 skipped, 110
  deselected`; the five POSIX race tests produced `5 passed, 111 deselected`.
  The expanded publisher contract produced `17 passed, 8 skipped, 91
  deselected` on Windows and `25 passed, 91 deselected` on Linux.
- Source races now cover in-place mutation after member snapshot, source
  directory replacement after pinning, and ancestor replacement with a
  symlink during component-by-component opening. Remote uploads are proven to
  use the private immutable copy.
- Receipt races cover target creation after parent open and parent directory
  replacement. The target is never overwritten, and writes remain bound to
  the pinned parent directory.
- Exit 76 now separates unknown commit state from exit 74. The
  `reconcile-complete-group` operation performs only provider stat/get calls,
  validates the downloaded lease and complete group privately, and creates a
  strict run/COMPLETE/lease-bound receipt without mutating provider state.
- The real disposable MinIO race now strictly parses the sole winner receipt,
  calls `validate_publish_receipt`, downloads the permanent lease and verifies
  `lease_id_hash`, and runs reconciliation while proving that the remote object
  key set is unchanged. This remains local same-machine concurrency evidence,
  not off-host evidence.
