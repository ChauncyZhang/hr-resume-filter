# Final E2E A report: UX-09 F-01 through F-06

## Status

`DONE_WITH_CONCERNS` — the isolated runner and its contract are implemented, but the real browser release gate is intentionally and correctly **FAIL/INCOMPLETE**. No F-01 through F-06 PASS is claimed.

The implementation is limited to `tests/e2e/**`, `deploy/e2e/**`, this report, and the existing E2E README. Product frontend/backend, governance, migrations, production Compose, backup/observability, parallel B2B3/publisher work, and the three protected user files were not edited by this task.

## Runner contract and isolation

- `tests/e2e/f01-f06.cjs` names F-01 through F-06 and executes desktop 1280x720 and mobile 390x844 contexts against the real UI.
- `deploy/e2e/run-final.ps1` requires `DISPOSABLE_E2E_CONFIRMED=1` and creates a random `ux09-final-e2e-<12 hex>` Compose project, free host ports, database and object-storage identities, synthetic `example.test` users, unique buckets/volumes, Chromium persistent profiles, and `.tmp/e2e-artifacts/<project>`.
- The runner builds the current checkout and starts PostgreSQL, MinIO, ClamAV, API, Worker, proxy, and Vite. It does not use fixture responses or API writes to impersonate UI flow completion.
- Success waits are event/response/locator/HTTP-poll based. There is no fixed browser sleep success condition.
- Non-PASS flows capture screenshot, trace, sanitized DOM/current URL, console/page errors, failed requests, and HTTP response method/path/status. Trace collection excludes initial login, account-switch login, and resume upload bodies.
- Cleanup removes only the random project and its volumes unless `-KeepOnFailure` is explicitly used.

TDD runner contract history:

1. Missing final runner files: RED, 0/5; initial implementation: GREEN, 5/5.
2. Cleanup, PowerShell RNG compatibility, Compose build context, exact login heading, and app-role reprovision contracts each reproduced RED before their focused fix and returned GREEN.
3. False-positive prevention for F-01 response status and F-02 non-retryable outcomes: RED, 4/5; GREEN, 5/5.
4. Real persistent Chromium profile usage: RED, 4/5; GREEN, 5/5.
5. Account-switch credential exclusion from F-05 traces: RED, 4/5; GREEN, 5/5.

Final focused result:

```text
node --test tests/e2e/final-runner-contract.test.cjs
tests 5, pass 5, fail 0, exit 0
```

## Real browser attempt

Command:

```powershell
$env:DISPOSABLE_E2E_CONFIRMED='1'
PowerShell -ExecutionPolicy Bypass -File deploy/e2e/run-final.ps1
```

Disposable project: `ux09-final-e2e-8e4d63536e5e`.

Observed infrastructure: migrations and synthetic preparation completed; PostgreSQL, MinIO, ClamAV, API, Worker, and proxy became healthy; the browser runner exercised both required viewports. The runner returned exit 2 and `run-final.ps1` reported `Playwright F-01 through F-06 gate was incomplete (exit 2)`. Containers, networks, test image, browser profiles, and named volumes were cleaned automatically. Untracked failure evidence remains under `.tmp/e2e-artifacts/ux09-final-e2e-8e4d63536e5e`.

### Exact flow result

| Flow | Desktop 1280x720 | Mobile 390x844 | Conclusion |
|---|---|---|---|
| F-01 | BLOCKED | BLOCKED | UI create/publish returned 201 and detail reads returned 200, but immediate edit `PUT /api/v1/job-definitions/{id}` returned 409 in both viewports. Edit and refresh persistence are not accepted. |
| F-02 | BLOCKED | FAILED before import | Desktop reached server terminal progress 18/18, but all 18 files were non-retryable failures; no candidate or retry control was produced. On mobile, the workbench navigation control existed in the DOM but Playwright reported it outside the 390x844 viewport. |
| F-03 | NOT REACHED | NOT REACHED | F-02 produced no real candidate/run prerequisite. Human conclusion, stage transition, duplicate/version conflict, and refresh persistence remain unverified. |
| F-04 | NOT REACHED | NOT REACHED | No F-03 candidate reached scheduling eligibility. Schedule/reschedule, conflict recovery, history, ICS download, and independent ICS parsing remain unverified. |
| F-05 | NOT REACHED | NOT REACHED | No F-04 interview/task existed. Draft restore, ambiguous/idempotent submit, own-only feedback, manual HR decision, and denial checks remain unverified. |
| F-06 | NOT REACHED | NOT REACHED | No completed upstream candidate existed. Pool membership, reactivation, source relation, destination persistence, and duplicate-active 409 remain unverified. |

Static UI/API inspection found corresponding product routes and handlers for all six flows. That is implementation-surface evidence only; it does not override the real gate failure or prove F-03 through F-06.

## Artifact privacy audit

The existing artifact directory and every expanded `trace.zip` were scanned as binary/text for required canaries, credentials, email/phone PII, authorization/session/API-key markers, and object-key markers.

- Required canaries `RESUME_BODY_CANARY`, `CSRF_CANARY`, `API_KEY_CANARY`, and `OBJECT_KEY_CANARY`: 0 matches.
- Chinese mobile phone pattern: 0 matches.
- Email values were limited to the synthetic interviewer `@example.test` identity and the UI placeholder `name@company.com`; no real candidate contact was found.
- **Concern:** both old F-05 traces captured the synthetic interviewer account-switch request and its random plaintext disposable password. Affected files are `desktop-F-05/trace.zip` and `mobile-F-05/trace.zip`. These artifacts are untracked, must not be shared, and are not part of the commit.
- The runner was subsequently changed under TDD to stop tracing before logout/login and restart only after authentication. This privacy correction has contract coverage but was not used to reinterpret or rerun the failed business gate as PASS.

## Verification and disposition

Fresh closeout commands and results:

```text
node --test tests/e2e/final-runner-contract.test.cjs tests/e2e/harness-contract.test.cjs
8 passed, 0 failed, exit 0

node --check tests/e2e/f01-f06.cjs
node --check tests/e2e/final-runner-lib.cjs
node --check tests/e2e/final-runner-contract.test.cjs
all exit 0

python -m py_compile deploy/e2e/prepare-final.py
exit 0

[scriptblock]::Create((Get-Content deploy/e2e/run-final.ps1 -Raw -Encoding UTF8))
PowerShell syntax OK, exit 0

(cwd docs/design/prototypes/ats-low-fi-option-2) npm.cmd test
267 passed, 0 failed, exit 0

(cwd docs/design/prototypes/ats-low-fi-option-2) npm.cmd run build
build succeeded, exit 0; existing >500 kB Vite chunk warning remains

git diff --check -- tests/e2e deploy/e2e .superpowers/sdd/task-final-e2e-report.md
exit 0
```

Self-review found no additional blocking defect in the scoped isolation, cleanup, or false-positive status handling. Non-blocking/known verification gaps are deliberate and visible: the post-audit trace-window correction has contract coverage but no new full-stack run, upload-time failures omit trace payload capture to avoid retaining resume bodies, and the unreachable F-03 through F-06 tails remain unverified behind the real F-01/F-02 prerequisites. These gaps do not change the real gate from FAIL to PASS.

The final handoff must retain these conclusions:

- Real gate: FAIL/INCOMPLETE, exit 2.
- Release blocker: F-01 edit conflict (409).
- Release blocker: desktop F-02 18/18 non-retryable failures with no candidate/retry path.
- Responsive blocker: mobile navigation is outside the required interactive viewport.
- F-03 through F-06: not reached and not verified.
- Existing pre-fix F-05 traces: privacy-tainted synthetic credentials; untracked and not distributable.

Only scoped E2E files are eligible for staging and commit. `.tmp/**`, product changes, B2B3/publisher work, and `.superpowers/sdd/task-1-report.md`, `.superpowers/sdd/task-2-report.md`, and `app/sample/candidates.csv` must remain unstaged.
