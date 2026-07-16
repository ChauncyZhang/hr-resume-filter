# UX-10 Feishu Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deployable, organization-scoped Feishu OAuth and calendar integration that is disabled by default and never creates ATS users.

**Architecture:** A focused `server.app.integrations.feishu` package owns provider contracts, encrypted organization configuration, OAuth state and bindings, calendar synchronization, and API routes. Existing identity sessions, RBAC, idempotency records, outbox delivery, trace IDs, and ATS interview records remain authoritative. The React/Vite prototype only exposes configuration, login, and binding status.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, cryptography, httpx, pytest, React 19, Vite, Node test runner.

## Global Constraints

- The integration and every organization configuration are disabled by default.
- OAuth may bind or log in only an existing active or invited ATS user; it never creates a user.
- API responses never include App Secret, verification token, encrypt key, access tokens, or decrypted values.
- OAuth state is random, stored only as a hash, expires, and is consumed once before code exchange.
- Freebusy requests contain at most 10 users and each provider call spans at most 14 days.
- ATS interview time and attendees are authoritative; provider-originated changes only set `pending_confirmation`.
- Tests use a fake provider and make no real network calls.
- Do not modify `InterviewViews.jsx`.

---

### Task 1: Persistence and provider contracts

**Files:**
- Create: `server/app/integrations/feishu/__init__.py`
- Create: `server/app/integrations/feishu/models.py`
- Create: `server/app/integrations/feishu/provider.py`
- Create: `server/app/integrations/feishu/service.py`
- Create: `server/migrations/versions/0019_feishu_integration.py`
- Test: `server/tests/test_feishu_contract.py`
- Test: `server/tests/test_feishu_migration.py`

**Interfaces:**
- Produces `FeishuProvider`, `FakeFeishuProvider`, `HttpFeishuProvider`, OAuth identity/value objects, freebusy chunking, calendar event operations, encrypted config models, one-time OAuth state, stable identity binding, and interview sync state.

- [ ] Write contract and migration tests for secret redaction, state consume-once, stable identity matching, no user creation, 10-user/14-day chunking, calendar idempotency, retry-safe status, and downgrade metadata.
- [ ] Run `python -m pytest server/tests/test_feishu_contract.py server/tests/test_feishu_migration.py -q` and confirm failures are caused by the missing module/revision.
- [ ] Implement the minimal models, provider adapters, and service behavior required by those tests.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Organization, OAuth, binding, and sync APIs

**Files:**
- Create: `server/app/integrations/feishu/api.py`
- Modify: `server/app/main.py`
- Modify: `server/app/identity/service.py`
- Modify: `server/app/identity/api.py`
- Modify: `server/app/queue/policy.py`
- Modify: `server/app/interviews/api.py`
- Test: `server/tests/test_feishu_api.py`

**Interfaces:**
- Produces organization-admin configuration/test endpoints, public login authorization/callback endpoints, authenticated binding/status/unbind endpoints, freebusy endpoint, outbox scheduling on interview create/update/cancel, and safe problem responses.

- [ ] Write API tests proving RBAC, validation, secret omission, disabled fallback, one-time state, existing/invited-only account resolution, binding conflicts, unbind, freebusy bounds, and safe provider failures.
- [ ] Run `python -m pytest server/tests/test_feishu_api.py -q` and confirm expected failures.
- [ ] Implement routes and minimal wiring, using existing CSRF, cookie, trace, outbox, and idempotency conventions.
- [ ] Re-run API and existing identity/interview tests.

### Task 3: React/Vite entry points

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/feishuIntegration.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/feishuIntegration.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/apiClient.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/LoginView.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ProfileSettings.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Produces a disabled-aware Feishu login button, organization configuration panel with masked secret status and connection test, and account binding/unbinding status.

- [ ] Write Node contract tests for API paths, secret-safe state mapping, disabled UI, login start, and binding status.
- [ ] Run `npm test -- --test-name-pattern=Feishu` in the prototype and confirm expected failures.
- [ ] Implement the minimal controllers and UI entry points without touching interview views.
- [ ] Run the prototype Node tests and Vite production build.

### Task 4: Verification and commit

**Files:**
- Modify only files listed above plus narrowly required test/bootstrap imports.

- [ ] Run focused Feishu backend tests, relevant identity/interview/backend migration tests, the complete frontend unit suite, and the frontend production build.
- [ ] Run `git diff --check`, inspect `git status --short`, and review the final diff for secret leakage or unrelated changes.
- [ ] Commit the scoped change with message `feat: add disabled Feishu integration skeleton` and report hash, files, tests, and residual deployment risks.
