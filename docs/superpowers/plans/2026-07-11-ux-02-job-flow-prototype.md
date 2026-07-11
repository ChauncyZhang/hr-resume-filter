# UX-02 Job Flow Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the selected ATS prototype with a complete, clickable position-management flow covering JOB-01, JOB-02, JOB-03, and navigation back to WB-01.

**Architecture:** Keep the existing React/Vite prototype and its shared shell. Add a focused `JobViews.jsx` module for position-specific screens and mock data, while `App.jsx` continues to own global navigation, notifications, and the existing workbench. Use in-memory state only; no server API or persistence is introduced in UX-02.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, in-app browser QA.

## Global Constraints

- Preserve the selected option-2 visual language and the user-approved larger typography.
- Use synthetic candidate and position data only.
- Keep all primary controls clickable; do not add production APIs or authentication.
- Validate at 1440 × 1024 and 390 × 844 with no body-level horizontal overflow.
- Use Chinese labels for all HR-facing interface text.

---

### Task 1: Position Views and Mock Domain Data

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/JobViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`

**Interfaces:**
- Consumes: `onNavigate(view, job?)`, `onNotify(message)`, and the current active position.
- Produces: `JobsWorkspace`, which renders `list`, `form`, or `detail` modes and calls `onCreate(job)` after a valid form submission.

- [ ] **Step 1: Add representative position records**

Define four positions with name, department, owner, priority, status, candidate counts, funnel counts, update time, and synthetic activity records.

- [ ] **Step 2: Add JOB-01 position list**

Implement status tabs, keyword search, owner/department filters, sortable-looking table columns, row selection, and row click navigation to JOB-03.

- [ ] **Step 3: Wire the shared shell**

Change the “职位” navigation item to render `JobsWorkspace`, and change “新建职位” to open the full JOB-02 screen rather than the earlier modal-only form.

- [ ] **Step 4: Verify JOB-01 manually**

Run the dev server, open the prototype, click “职位”, search for “AI”, filter by status, and open a position detail. Expected: the list updates without a page reload and context is preserved.

### Task 2: Position Creation and Editing

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/JobViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: optional position data for edit mode.
- Produces: a validated job draft containing `name`, `department`, `headcount`, `owner`, `priority`, `jd`, `mustHave`, `niceToHave`, `process`, and `llmEnabled`.

- [ ] **Step 1: Implement the segmented JOB-02 form**

Create sections for basic information, public JD, extracted must-have/nice-to-have criteria, hiring process, and AI assistance. Keep a sticky progress summary beside the form on desktop.

- [ ] **Step 2: Implement form states**

Show field-level validation for missing position name or JD, simulated JD extraction progress/success, save-draft feedback, and publish success.

- [ ] **Step 3: Implement safe navigation**

When the form is dirty, show an in-app confirmation dialog for save draft, discard, or continue editing.

- [ ] **Step 4: Verify JOB-02 manually**

Open the form, submit it empty, fill required fields, trigger JD extraction, save a draft, and publish a position. Expected: validation is local and published positions return to JOB-01.

### Task 3: Position Detail and Funnel Management

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/JobViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: selected position and its funnel/activity data.
- Produces: JOB-03 tabs for candidate funnel, position information, collaboration activity, and settings.

- [ ] **Step 1: Add the detail header and metrics**

Show position state, owner, department, headcount, update time, candidate total, pending review, interviewing, and pending decision.

- [ ] **Step 2: Add detail tabs**

Implement a candidate funnel view with stage counts and representative candidate rows, a JD/info view, an activity timeline, and a settings summary.

- [ ] **Step 3: Connect primary actions**

Make “导入简历”, “编辑职位”, “暂停招聘/恢复招聘”, and candidate-row navigation produce visible state changes or open the existing relevant prototype interaction.

- [ ] **Step 4: Verify JOB-03 manually**

Open all detail tabs, pause and restore the position, open edit mode, and trigger resume import. Expected: each action provides explicit feedback and preserves the selected position.

### Task 4: Responsive and Design QA

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/implementation-1440x1024-final.png`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/implementation-390x844-final.png`

**Interfaces:**
- Consumes: final JOB-01, JOB-02, and JOB-03 browser states.
- Produces: reproducible browser evidence and `final result: passed` only when no P0/P1/P2 issue remains.

- [ ] **Step 1: Run the production build**

Run: `npm.cmd run build`
Expected: Vite exits with code 0.

- [ ] **Step 2: Capture desktop states**

Capture JOB-01, JOB-02, and JOB-03 at 1440 × 1024. Check typography, clipping, table density, right-side form summary, and body overflow.

- [ ] **Step 3: Capture the mobile state**

Capture JOB-01 and JOB-03 at 390 × 844. Check navigation drawer, action wrapping, table fallback, tap targets, and no body-level horizontal overflow.

- [ ] **Step 4: Update QA and commit**

Record interactions, console errors, findings, fixes, and final evidence in `design-qa.md`; run `git diff --check`; commit the scoped UX-02 changes.
