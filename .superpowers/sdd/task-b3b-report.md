# Task B3B Report

## Status

Implemented the candidate deletion and legal-hold frontend in the B3B-owned
files. B3A commit `ee16d94` is present and the frontend consumes its optional
`legal_hold_id` / `legal_hold_version` governance-status fields without changing
backend code.

## Files changed

- `docs/design/prototypes/ats-low-fi-option-2/src/candidateGovernance.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/candidateGovernance.test.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/governanceSettings.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/governanceSettings.test.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- `docs/design/prototypes/ats-low-fi-option-2/src/roleCapabilities.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/roleCapabilities.test.js`
- `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`
- `.superpowers/sdd/task-b3b-report.md`

No backend, deployment, B2B1, or protected user file was modified or staged by
B3B. The optional browser-audit script was not created because the current
local real-backend stack could not enter an authenticated session.

## UI behavior and action hierarchy

- Server-backed candidate detail now loads governance status on candidate or
  role changes, cancels superseded work, and suppresses stale responses.
- The compact candidate governance section exposes loading, safe error/retry,
  deletion status, legal-hold status, and the hold reason only when returned.
- The primary destructive action is explicit “请求删除” confirmation. It states
  that submission requires approval and does not delete immediately.
- Successful deletion requests show all nine safe impact counts and the backup
  window. Open requests disable duplicate submission.
- Recruiting administrators can place and release holds. Both reasons require
  1..1000 non-whitespace characters; approved deletion receives an explicit
  queued-deletion warning. Release remains disabled without B3A's hold ID and
  version.
- Settings > Audit and Data Governance contains the existing-IA deletion queue,
  status filtering, cursor pagination, loading/empty/error/retry states, and a
  request-only detail drawer. It never joins or links candidate names.
- System administrators receive explicit approval/re-approval confirmation for
  `requested` and `failed` rows. Stale manifest/version conflicts re-fetch the
  request, mark the impact changed, and require another confirmation.

## Request safety

- Exact API paths, bodies, quoted `If-Match`, and idempotency options are
  controller-tested.
- Idempotency keys remain stable after network/5xx ambiguity and rotate after
  success, definitive 4xx, or intent/version changes.
- Normalizers project only documented governance fields. Raw problem details,
  manifests, storage keys, credentials, and unknown response fields are not
  rendered.
- Successful candidate mutations refresh governance status and the current
  deletion request. Candidate/role changes, unmount, and disposal abort or
  suppress obsolete work.

## Roles

- `system_admin`: deletion queue and approval only; no candidate governance
  controls.
- `recruiting_admin`: candidate status, deletion request, and hold management;
  no approval control.
- `recruiter` / HR: candidate status and deletion request; no hold or approval.
- `hiring_manager`: candidate status only when the server authorizes the read.
- interviewer and unknown roles fail closed.

Separate helpers cover status read, deletion request, approval queue, and legal
hold management; retention-edit capability is not reused.

## Accessibility and responsive behavior

- Destructive dialogs use `role=dialog`, `aria-modal`, explicit labels, initial
  focus, Tab trapping, focus restoration, and pending-state Escape/close gates.
- New operational body text and form controls use at least 16 px text.
- Request IDs, safe codes, and count labels wrap within their containers.
- 390x844 in-app browser inspection of the reachable unauthenticated shell
  measured viewport width 390 and document/body scroll width 390 with no
  console warning/error.
- Governance dialog/drawer 390 px CSS uses full-width controls, one-column
  impact grids, and no fixed-width request rows.

## Verification

TDD RED was observed before implementation:

```text
node --test src/candidateGovernance.test.js src/roleCapabilities.test.js src/governanceSettings.test.js
```

Result: missing module/exports/controller methods produced 8 expected failures.
A later focused RED reproduced a stale-conflict bug where `approving` remained
true after refresh; the new assertion failed `true !== false` before the fix.

Focused GREEN:

```text
node --test src/candidateGovernance.test.js src/roleCapabilities.test.js src/governanceSettings.test.js
```

Result: 46 passed, 0 failed.

Complete frontend suite:

```text
npm.cmd test
```

Result: 263 passed, 0 failed.

Production build:

```text
npm.cmd run build
```

Result: Vite build succeeded. The existing chunk-size warning remains; no build
error occurred.

Scoped whitespace check:

```text
git diff --check
```

Result: passed. Git emitted only the pre-existing protected CSV line-ending
warning; that file was not touched or staged by B3B.

## Browser gate and remaining risk

B3A is merged, but the currently running local stack at `127.0.0.1:8080`
returns `403 csrf_validation_failed` for the initial `GET /api/v1/me` and the
checkout provides no browser test credentials to reuse. Therefore the required
real-backend HR request -> system-admin approval -> recruiting-admin
hold/release, denied-control, refresh-recovery, and authenticated 390 px dialog
gate could not be run without bypassing authentication or inventing secrets.

The remaining frontend risk is limited to authenticated visual/integration
behavior against a newly seeded real stack. Controller contracts, role denial,
focus behavior, complete frontend regression, production compilation, and the
reachable 390 px shell were verified independently.
