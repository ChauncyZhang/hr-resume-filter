# Phase 5 Talent Review Fixes Report

## Status

Complete. All seven Important findings in `phase5-talent-review-fixes-brief.md` are addressed.

## Changed files

- `server/app/talent/api.py`
- `server/app/recruiting/service.py`
- `server/migrations/versions/0014_talent_pools.py`
- `server/tests/test_talent_api.py`
- `server/tests/test_talent_api_postgres.py`
- `server/tests/test_talent_migration.py`
- `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/talentController.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/talentController.test.js`
- `.superpowers/sdd/phase5-talent-review-fixes-report.md`

## Fix evidence

- Reactivation accepts only resumes already visible through an authorized application at the download boundary; default and override resumes share this check.
- Membership source applications are loaded through the caller's job scope. A later permission loss returns only `{id, redacted: true}` and the frontend does not reconstruct job, stage, or conclusion fields.
- Ordinary application creation and talent reactivation both lock the candidate aggregate. Only PostgreSQL violation `uq_applications_active` is translated to `409 active_application_exists`.
- Downgrade from `0014` records `application.source_detached_for_downgrade` before clearing a cross-job source link that revision `0013` cannot represent.
- Server-backed candidate details open an explicit talent-pool selector. Missing or stale pool IDs fail; there is no first-pool fallback.
- `granted` visibility was removed from the creation UI and is rejected by the controller until grantee selection exists.
- Pending create/add/reactivate commands retain both one idempotency key and the original request body after an ambiguous response. Success or a definitive failure clears the pending operation.
- Idempotent replay assertions cover application, application event, candidate event, audit, idempotency, contact, file, and resume counts.

## TDD evidence

- Backend red: `server/tests/test_talent_api.py` initially failed because an unauthorized source application returned `201` instead of `404` (`1 failed, 5 passed`).
- Frontend red: `src/talentController.test.js` initially failed on missing selection/idempotency exports, then on missing explicit candidate eligibility and redaction behavior.
- PostgreSQL red: the mixed-writer fixture initially produced `201/404`; after making both writers independently authorized, the race verified the intended `201/409` behavior.

## Verification

- `docker run --rm -v "${PWD}:/workspace" -w /workspace ux09-server-test python -m pytest server/tests/test_talent_api.py server/tests/test_recruiting.py server/tests/test_recruiting_api.py -q`
  - `76 passed in 62.81s`
- Isolated PostgreSQL database created with a UUID name, then:
  - `python -m pytest server/tests/test_talent_api_postgres.py server/tests/test_talent_migration.py -q`
  - `3 passed in 24.71s`; isolated database force-dropped afterward.
- `npm test` in `docs/design/prototypes/ats-low-fi-option-2`
  - `216 passed, 0 failed`
- `npm run build` in `docs/design/prototypes/ats-low-fi-option-2`
  - Passed; Vite emitted the existing non-blocking chunk-size warning (`520.13 kB`).
- `docker run --rm -v "${PWD}:/workspace" -w /workspace ux09-server-test python -m compileall -q server/app/talent server/app/recruiting/service.py server/tests/test_talent_api.py server/tests/test_talent_api_postgres.py server/tests/test_talent_migration.py`
  - Passed with no output.
- `git diff --check`
  - Passed.

## Remaining concern

- The frontend production bundle remains above Vite's 500 kB warning threshold; this is non-blocking and outside the talent review-fix scope.
