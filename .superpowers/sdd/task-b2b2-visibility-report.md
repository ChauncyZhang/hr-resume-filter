# B2B2 tombstone visibility report

## Owned implementation

- Added `Candidate.deleted_at IS NULL` to the shared ordinary-business candidate predicate.
- Closed direct candidate loaders across recruiting, screening, talent, and interviews.
- Added candidate-row locking plus a post-lock tombstone check before ordinary mutations.
- Prevented stale parse, score, retry, bulk action, and LLM jobs from processing tombstoned candidates.
- Kept job funnel and other non-PII historical aggregates unchanged.
- Governance APIs and governance deletion code were not changed.

## Verification

- `test_recruiting_api.py test_recruiting_hardening.py test_workbench_api.py test_candidate_tombstone_visibility.py`: 131 passed before the final test expansion.
- `test_screening_api.py test_screening_actions.py`: 19 passed.
- `test_screening_pipeline.py`: 15 passed.
- `test_llm_pipeline.py`: 26 passed.
- `test_talent_api.py`: 7 passed.
- `test_interview_api.py`: 26 passed.
- `test_recruiting.py test_candidate_tombstone_visibility.py`: 29 passed after the final fixture and coverage updates.
- PostgreSQL-specific focused files: 9 skipped because the available test container had no PostgreSQL fixture.
- `compileall` and scoped `git diff --check`: passed.
- Non-topology backend split: 753 passed, 118 skipped, 10 failed before the service-fixture correction. Seven failures were the now-corrected recruiting unit fixtures; the remaining three require `git` or Docker CLI inside the test container and are unrelated to this slice.

## Remaining risk

- PostgreSQL `FOR UPDATE` behavior was code-reviewed but not exercised against a live PostgreSQL service in this worktree.
- The complete split was not rerun after correcting the seven unit fixtures; all affected tests and all owned focused modules passed independently.

## Visibility review follow-up

- Added a two-way deletion barrier for rule scoring and LLM scoring. Each claim and finalize transaction locks `Candidate` before `ScreeningItem`, rejects tombstoned candidates and deletion requests in `approved`, `executing`, or `completed`, and commits the running state before external work starts.
- LLM provider calls run after the claim session closes. A deletion approved while the provider is running causes the response to be discarded without an invocation or evaluation row.
- Rule scoring computes outside the claim transaction and rechecks the same barrier before writing a result. Parse checks the barrier before beginning and again before candidate association.
- Retry and bulk mutations preserve the ordinary non-enumerating `404 resource_not_found` contract when the candidate becomes unavailable after the initial API lookup.
- Atomic claims only transition `queued -> running` for LLM and `parsed -> scoring` for rule scoring; duplicate workers do not repeat provider or scoring work.

### Follow-up verification

- `test_screening_actions.py test_screening_api.py`: 19 passed.
- `test_candidate_tombstone_visibility.py`: 12 passed.
- `test_screening_pipeline.py test_llm_pipeline.py`: 41 passed.
- `test_recruiting.py`: 22 passed as an adjacent visibility regression gate.
- `test_screening_actions_postgres.py`: 3 skipped because `POSTGRES_SMOKE_URL` is not configured.
- The lock-order unit gate compiles the emitted statements with the PostgreSQL dialect and verifies `Candidate FOR UPDATE -> active deletion lookup -> ScreeningItem FOR UPDATE`.
- Live PostgreSQL lock waiting remains unexecuted; no configured disposable PostgreSQL fixture was available.

## Parse finalize review follow-up

- A parse that committed `parsing` now treats a finalize-time tombstone or active deletion as a successful terminal discard. The short finalize transaction locks `Candidate -> ScreeningItem -> ScreeningRun`, sets the item to `cancelled` with `candidate_unavailable`, aggregates run progress, and commits without creating a candidate, resume, application, or parsed-text row.
- A repeated callback observes the terminal `cancelled` item under the same candidate-first barrier and returns without changing timestamps, run version, or counts.
- Single-item cancellation settles the run as `failed` with counts `(processed=1, succeeded=0, failed=1)`; a run containing one successful item and one cancelled parse settles as `partial` with `(2, 1, 1)`.
- The test parser activates the deletion barrier from a separate database session only after observing committed `parsing`, verifying that scanning/parsing remains outside the claim and finalize transactions.

### Parse finalize verification

- RED: the three new finalize-barrier cases failed with `PermanentJobError("screening_item_missing")` from the old finalize path.
- GREEN: `test_candidate_tombstone_visibility.py -k parse_finalize_barrier`: 3 passed.
- Focused regression: `test_candidate_tombstone_visibility.py test_screening_pipeline.py`: 30 passed.
