# Task B2B2 Report — Governance deletion core execution

## Result

B2B2 implements the governed candidate-deletion worker from strict queue dispatch through exact artifact deletion, B2B1 database redaction, canonical signed-ledger verification, and atomic completion. B2B1 remains the database-redaction boundary; Phase 6C and ordinary recruiting, screening, talent, and interview read/write paths are outside this change.

## Execution contract

- The handler accepts only the exact tenant, deletion-request, and request-version payload shape.
- Candidate and deletion request are locked in Candidate-to-DeletionRequest order. Version, state, legal hold, active applications, and the private manifest are revalidated before execution starts or resumes.
- Candidate-associated ScreeningItems are then locked in stable order. Live parse, score, or LLM queue leases force a retry before execution side effects; matching queued jobs are cancelled and running jobs are never cancelled. Expired leases do not create a permanent block. The companion screening guard uses the same Candidate-to-ScreeningItem order and rejects new provider/scoring work after approval or execution begins.
- Approval transitions to `executing`, exact artifacts are materialized, and the started audit is committed in one short transaction.
- Report exports persist exact candidate membership. Pre-0017 exports have no inferred membership. Matching queued jobs are cancelled; running or leased jobs force a safe retry before any object deletion.
- Report generation uses prepare, object write, and token-checked finalize phases so a cancelled or stale writer cannot publish a late export.
- Resume and matching temporary-export objects are deleted outside database transactions. Each object has an independent short checkpoint transaction; missing objects are successful and retries resume from persisted checkpoints.
- B2B1 governance-role redaction runs only after every artifact checkpoint is deleted. Its checksum and the ledger construction facts are persisted so a later ledger failure retries byte-identically.
- The canonical signed ledger is written last, read back, and independently verified. Existing content must match exactly and have a valid signature. Completion requires a verified receipt.
- `completed` and its audit event commit together. Completed redelivery only verifies the ledger and does not increment recovery generation.
- Dead-letter callbacks match tenant, request, version, and `executing` exactly. They do not acquire a Candidate lock while the queue row is locked, avoiding the Queue-to-Candidate lock inversion.

## Data and migration

Migration `0017_governance_deletion` adds exact report-export membership and report generation tokens, plus stable database-redaction checksum and ledger receipt fields on deletion requests. Constraints require complete ledger receipt facts for completed requests. The downgrade removes the additive B2B2 objects and columns.

## Verification evidence

- Focused governance/report/queue/worker/settings unit split: `207 passed, 5 skipped in 106.54s`.
- Core worker/report rerun after concurrent workspace changes: `23 passed, 1 skipped in 36.65s`.
- Screening-aware deletion worker unit gate: `20 passed, 1 skipped in 41.35s`.
- Final governance deletion/report focused unit gate: `29 passed, 1 skipped in 40.49s`.
- Reverse screening active-deletion gate from the shared visibility work: `10 passed in 25.97s`.
- PostgreSQL atomic score-job claim before deletion claim: `1 passed in 12.27s`.
- PostgreSQL migration suite: `11 passed, 1 skipped in 190.07s`.
- PostgreSQL concurrent claim: `1 passed in 12.98s`.
- PostgreSQL governance-role denial: `2 passed in 9.34s`.
- Fresh real MinIO B2B1 role/race gate: `2 passed in 1.77s`.
- Fresh real MinIO B2B2 deletion ordering, ledger fail/retry, read-back verification, and tamper rejection, plus ledger race: `3 passed in 7.96s`.
- Committed-version rerun on a new isolated MinIO instance: `1 passed in 6.48s`; the instance and network were removed after the gate.

The broad backend split was intentionally not used as completion evidence: an older long-running container was stopped because it occupied the shared PostgreSQL instance. Per task direction, completion is based on the focused unit, real PostgreSQL, and real MinIO gates above.

## Remaining risk

The focused integration evidence proves the PostgreSQL governance boundary and the real MinIO object/ledger ordering independently. It does not run one monolithic end-to-end test with both external services in the same process. Operational recovery therefore still depends on the deployed worker receiving the documented distinct delete-only, ledger-only, and governance database credentials.
