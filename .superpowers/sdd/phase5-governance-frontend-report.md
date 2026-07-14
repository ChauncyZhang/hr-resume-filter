# Phase 5 Governance Task A - Frontend Report

## Result

Implemented the Task A governance frontend slice against the backend governance schemas and API routes. The existing SET-04 settings layout now uses real audit-log and retention-policy requests; no backend, navigation, AI settings, Task B deletion, or legal-hold code was changed.

## TDD evidence

### RED

- Controller/role RED: `node --test` surfaced 16 governance controller failures because the new module was absent and the role suite failed because the explicit governance capability exports did not exist.
- UI RED: the SET-04 source test failed because `SettingsViews.jsx` still used synthetic audit rows and local retention state.
- Conflict RED: the version-conflict test showed `saveRetention()` incorrectly returned success after reloading the current policy.
- Scope-isolation RED: the UI source test showed governance settings did not remount on role changes, leaving a possible one-frame stale-scope render.

### GREEN

- Focused controller/role tests: 27/27 passed.
- Full frontend suite: 244/244 passed.
- Vite production build completed successfully.
- `git diff --check` exited 0. It emitted only the pre-existing CRLF warning for prohibited user file `app/sample/candidates.csv`; that file was not touched or staged.

## Files

Created:

- `docs/design/prototypes/ats-low-fi-option-2/src/governanceSettings.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/governanceSettings.test.js`
- `.superpowers/sdd/phase5-governance-frontend-report.md`

Modified:

- `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/roleCapabilities.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/roleCapabilities.test.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

## Behavior and action hierarchy

- Default governance state loads audit records and retention policy independently.
- Audit filter reload is the primary audit action; it immediately clears old-scope rows. Cursor paging is secondary and appends/deduplicates records by audit ID.
- Audit exposes real loading, retryable error, empty, denied, paging, and safe detail-drawer states.
- Retention loads into a three-field draft (`terminal_days`, `talent_pool_days`, `backup_window_days`, each `30..3650`).
- Increasing values saves directly. Shortening first requests a server preview and then requires explicit destructive confirmation using the server count and expiry.
- System administrators can edit retention. Recruiting administrators and HR roles receive read-only policy and permission messaging. Other roles are denied governance access.
- Role changes remount the governance view so an old role's rows cannot render under a new role.

## Safety, accessibility, and responsive behavior

- Normalization retains only the documented audit and retention projection. Unknown fields, raw metadata, candidate/contact data, IP values, and server error detail are discarded.
- The UI renders `network_ref` as “网络标识” and never renders raw metadata.
- Loading/status/error regions use status or alert semantics; form fields have visible labels; dialogs keep the existing accessible SET-04 dialog pattern; destructive confirmation controls are disabled while saving.
- Existing mobile table/card and drawer behavior is preserved. Added governance filters stack at the existing mobile breakpoint, and long safe resource references wrap within their containers.
- Audit rows and preview tokens remain in memory only. Preview tokens are excluded from public controller state and cleared by draft changes and cleanup.

## API assumptions

- Consumes the exact backend routes and field names in `server/app/governance/schemas.py` and `server/app/governance/api.py`.
- PATCH sends a quoted loaded version through `If-Match` and one stable `Idempotency-Key` per logical save intent.
- Ambiguous unavailable failures retain the body/key; confirmed terminal failures and success reset them. Version conflicts reload policy and require review.
- The server remains authoritative for audit row authorization; display roles are used only for frontend affordances.

## Checks run

- `node --test src/governanceSettings.test.js src/roleCapabilities.test.js`
- `npm.cmd test` — 244 passed, 0 failed
- `npm.cmd run build` — success; existing bundle-size warning remains
- `git diff --check` — exit 0
- Local Vite preview opened in the browser; login page rendered with no console warnings/errors.

## Remaining frontend risk

- The authenticated governance screen was not visually traversed in the browser because the preview uses the real login/session flow and no credentials were introduced or bypassed. Controller, source-level UI, full-suite, and production-build checks cover the implementation; authenticated end-to-end visual QA remains the only gap.
- Vite continues to report the existing JavaScript chunk-size warning above 500 kB; this slice does not add a new routing or code-splitting policy.
