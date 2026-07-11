# UX-07 Reports, Settings, and Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver REP-01 and SET-01 through SET-04 as one navigable, role-aware prototype with report drill-down, risk confirmations, and responsive states.

**Architecture:** Add pure report aggregation and permission helpers with Node tests, then build focused `ReportViews.jsx` and `SettingsViews.jsx` modules. `App.jsx` owns global role simulation and cross-page navigation only; settings modules own synthetic configuration state and reuse the global notification pattern.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, Node `node:test`, in-app browser QA.

## Global Constraints

- Preserve the existing ATS shell and 24/18/16/14/13/12px typography scale.
- Use synthetic data only; never store or display a real API key.
- Reuse the existing candidates page for report drill-down.
- Keep report chart values accessible through text and tables.
- Require confirmation for permission expansion, external Provider enablement, and retention shortening.
- Verify 1280px desktop and 390px mobile without body-level horizontal overflow.

---

### Task 1: Report and Permission Domain Helpers

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ux07Domain.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ux07Domain.test.js`

**Interfaces:**
- Consumes: candidate records, report filters, and role strings `招聘管理员 | HR | 面试官`.
- Produces: `filterReportCandidates`, `buildReportMetrics`, `getRoleCapabilities`, and `isPermissionExpansion`.

- [x] **Step 1: Write failing domain tests**

Cover candidate filtering, metric consistency, interviewer report denial, HR read-only settings, administrator edit rights, and permission-expansion detection.

- [x] **Step 2: Run `npm test` and confirm RED**

Expected: failure because `ux07Domain.js` does not exist.

- [x] **Step 3: Implement minimal pure helpers**

Return deterministic metrics and explicit capability flags without browser or React dependencies.

- [x] **Step 4: Run `npm test` and confirm GREEN**

Expected: all domain and existing résumé tests pass.

### Task 2: REP-01 Report Workspace

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ReportViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: `candidates`, `positions`, `currentRole`, `onDrillDown({ position, stage })`, and `onNotify`.
- Produces: report filters, KPI metrics, funnel, stage efficiency, screening quality, interview efficiency, data tables, and report states.

- [x] **Step 1: Build unified filters and applied-condition summary**

Add date, position, department, and owner controls; clear filters restores the default dataset.

- [x] **Step 2: Build metrics and accessible report sections**

Render KPI values, funnel buttons, duration bars, screening rates, interview metrics, legends, and matching data tables.

- [x] **Step 3: Add drill-down and role states**

Route funnel clicks into the existing candidate list with position/stage filters. Interviewers see a no-permission state; HR sees only owned scope.

- [x] **Step 4: Add loading, empty, and module-error demonstrations**

Use stable skeletons, clear-filter recovery, and module-level retry without clearing filters.

### Task 3: SET-01 and SET-02 Organization and Templates

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: `currentRole`, `onRoleChange`, `onNotify`, and permission helpers.
- Produces: settings secondary navigation, organization tables, user editor, department view, workflow templates, rejection reasons, and interview templates.

- [x] **Step 1: Build settings shell and role simulator**

Keep the global page title and add a left secondary navigation with role switching and contextual permission notices.

- [x] **Step 2: Build organization and permission management**

Support user search/filter, edit drawer, department data, disabled users, and confirmation before expanding position scope.

- [x] **Step 3: Build workflow and evaluation templates**

Support stage editing, protected in-use stages, rejection reasons, interview dimensions, simulated save failure, retained draft, and retry.

- [x] **Step 4: Enforce read-only and denied role states**

HR receives read-only organization/templates; interviewers receive only read-only interview-template access.

### Task 4: SET-03 and SET-04 AI, Audit, and Retention

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: current role, synthetic provider config, audit records, and retention policies.
- Produces: masked API configuration, connection testing, external-provider confirmation, audit filters/details, retention edit, and shortening confirmation.

- [x] **Step 1: Build AI settings and masked secret behavior**

Show enablement, Provider, model, Base URL, masked key, replacement input, authorized positions, and nearby test states.

- [x] **Step 2: Build Provider risk confirmation and unsaved state**

Enabling an external Provider requires impact confirmation; leaving dirty settings offers continue, discard, or save draft.

- [x] **Step 3: Build audit table and detail drawer**

Filter by time, actor, action, and object; expose result, masked IP, Trace ID, and change summary.

- [x] **Step 4: Build retention policies and shortening confirmation**

Show policy scopes and cycles; shorter retention displays affected records and irreversible impact before save.

### Task 5: Responsive QA, Documentation, and Integration

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Create: report/settings desktop and mobile evidence screenshots.

**Interfaces:**
- Consumes: completed REP-01 and SET-01 through SET-04.
- Produces: verified UX-07 workflow, evidence, and merged main-branch commit.

- [x] **Step 1: Verify report desktop/mobile flows**

Test filters, data consistency, drill-down, loading/empty/error/permission states, and 1280/390 layouts.

- [x] **Step 2: Verify all settings flows**

Test role matrix, user edit confirmation, protected stages, save retry, masked key, Provider confirmation, audit detail, and retention confirmation.

- [x] **Step 3: Update documentation and evidence**

Record screenshots, interaction matrix, console status, and remaining P3 findings.

- [x] **Step 4: Run final gates and merge**

Run `npm test`, `npm run build`, and `git diff --check`; commit `Add UX-07 reports and settings workflow`, merge locally to `main`, rerun tests/build, and remove the worktree.
