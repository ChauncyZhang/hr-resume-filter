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
