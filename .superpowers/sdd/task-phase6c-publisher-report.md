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
- Config and source files are opened with no-follow/inode checks and copied
  into a process-private directory. Child environment inheritance is reduced;
  provider stdout/stderr is captured and never emitted.
- One random lease is written with provider-native `If-None-Match:*` under the
  fixed bucket-private lease prefix. There is no list-then-write lease path.
  The lease is never deleted. Existing lease/complete groups exit 75.
- Payload members are uploaded and independently size/SHA-256 verified by
  stat plus private download. COMPLETE is uploaded and verified last. A failed
  partial upload has no COMPLETE and cannot be retried or overwritten because
  its lease remains.
- The local receipt has exactly the foundation schema and binds the run ID,
  COMPLETE SHA-256, committed state, and SHA-256 of the unlogged random lease.
  Safety rejection is 78 and provider/verification failure is 74; all output is
  generic and contains no destination object, source filename, config, client
  stderr, credential, or lease value.

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
network, disposable MinIO container, and publisher runner. Credentials were
random, file-only, omitted from command arguments/output, and destroyed with
the containers. Two independent `docker exec` publisher processes raced the
same run ID.

Command:

```powershell
$env:UX09_RUN_MINIO_PUBLISHER_TEST='1'
$env:UX09_BACKUP_PUBLISHER_IMAGE='ux09-backup:phase6c-publisher-test'
python -m pytest server/tests/test_backup_restore_contract.py::test_s3_publisher_real_disposable_minio_two_process_race -q
```

Result: `1 passed in 7.61s`. Exactly one process returned 0 and one returned
75. One permanent lease remained, the immutable final group contained exactly
the expected members, the winner payload was preserved, exactly one bound
receipt existed, and COMPLETE metadata was not earlier than any payload.
The same Linux gate also rejected a 0640 config, config symlink, config
hardlink, and source-directory symlink with exit 78 before provider mutation.

This is a same-machine disposable MinIO concurrency proof. It is explicitly
not off-host storage evidence and does not satisfy the production provider gate.

## Readiness, rollback, and observability

The publisher adapter is ready for provider-specific integration, not launch.
Restore-point freshness remains the user-impacting SLI: page when no valid
complete point exists by 18 hours and before the 24-hour RPO is exhausted.
Track aggregate exit 75 conflicts, exit 74 provider/verification failures, exit
78 safety rejections, receipt failures, and completed restore-point age without
high-cardinality object/source labels.

Rollback is defined before rollout: stop new launches and restore the refusing
rclone publisher configuration. Preserve leases and partial groups; never
delete a lease to force retry. After remediation, use a fresh run ID for one
canary before restoring the 12-hour schedule.

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
  `$env:UX09_RUN_MINIO_PUBLISHER_TEST='1'; python -m pytest server/tests/test_backup_restore_contract.py -q`
  -> `101 passed, 5 skipped in 12.04s`. Remaining skips are pre-existing or
  unavailable Windows-only capability cases; the Linux publisher checks ran.
- `docker build --pull=false -t ux09-backup:phase6c-publisher-test deploy/backup`
  -> success; final local test image ID
  `sha256:b19cc9b324e7876f2272ae4ee6e907edd19a18455b14ef87761b3fa50d814ba8`.
- Git Bash `bash -n` for every `deploy/backup/*.sh`, in-memory Python compile
  for the publisher/test, and image executable check -> success.
- Generated `__pycache__`/`.pyc`/`.pyo` scan and sensitive-value scan -> clean.
- `git diff --check` -> success; its only output was an unrelated protected
  CSV line-ending warning. Final staged allowlist and commit are recorded in
  the handoff.
