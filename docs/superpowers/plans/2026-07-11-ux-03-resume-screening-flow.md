# UX-03 Resume Import and Screening Task Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete clickable resume import and AI screening flow covering IMP-01 and SCR-01 inside the selected ATS prototype.

**Architecture:** Add a focused `ScreeningViews.jsx` module that owns import wizard state, synthetic files, task progress, result filtering, and retry behavior. `App.jsx` remains responsible for global navigation and switches between the originating page and SCR-01. State is in-memory with a localStorage snapshot for recent-task recovery.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, browser-based interaction QA.

## Global Constraints

- Preserve the selected option-2 visual system and approved 12–14 px operational typography.
- Show current file progress as completed/total and current filename; do not use a fake percentage alone.
- Keep rule score and LLM score visually and semantically separate.
- A single parse or LLM failure must not fail the whole batch.
- Use synthetic files and candidate data; do not upload real personal data.
- Validate 1440 × 1024, 1280 × 720, and 390 × 844 layouts.

---

### Task 1: IMP-01 Import Wizard

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: active position name, available positions, and `onCreateTask(task)`.
- Produces: a task with ID, source, batch note, five validated file records, LLM setting, creator, and creation time.

- [ ] **Step 1: Build wizard structure**

Implement three steps: batch information, file validation, and confirmation. Show the current step, completed steps, and back/next actions.

- [ ] **Step 2: Build file validation**

Provide a synthetic five-file selection, file type/size summary, duplicate warning, one unsupported-file example, remove action, and a blocking explanation until invalid files are removed.

- [ ] **Step 3: Build confirmation and task creation**

Show target position, legal source, batch note, valid file count, total size, rule evaluation, LLM evaluation, and privacy reminder. Create SCR-01 only after validation succeeds.

- [ ] **Step 4: Connect all import entry points**

Route workbench, JOB-03, and empty-position actions to the same IMP-01 component while preserving the selected position.

### Task 2: SCR-01 Progress and Recovery

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`

**Interfaces:**
- Consumes: the created task and `onBack()`.
- Produces: per-file states, task status, rule/LLM results, retry actions, and bulk-operation feedback.

- [ ] **Step 1: Implement deterministic task progression**

Advance files through parsing, rule scoring, and LLM scoring. Persist completed/total, current stage, current filename, elapsed time, and task ID. Keep the page usable while running.

- [ ] **Step 2: Implement partial failure**

Produce one parse failure and one LLM partial success. Show human-readable reasons, trace IDs as secondary text, preserved rule scores, and isolated retry buttons.

- [ ] **Step 3: Implement task recovery**

Write the latest task snapshot to localStorage. On a later import entry, offer “继续最近任务” and restore task ID, status, and file results.

- [ ] **Step 4: Verify progress and retries**

Observe completed/total advancing, wait for partial success, retry parse and LLM failures, and confirm the task reaches complete without reprocessing successful files.

### Task 3: Result Review and Bulk Actions

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: finalized or partially finalized file records.
- Produces: filtered rows, selected IDs, and visible feedback for advance, reject, tag, talent-pool, export, and undo actions.

- [ ] **Step 1: Build result filters**

Support all, processing, success, partial success, and failed states plus keyword search. Show status counts and preserve separate rule and LLM score columns.

- [ ] **Step 2: Build result rows**

Show candidate/file, current state, recommendation, rule score, LLM score, matched requirements, missing requirements, risk, and row actions.

- [ ] **Step 3: Build bulk action bar**

Allow selecting completed rows and simulate advance to review, reject, add tag, add to talent pool, export, and short-lived undo feedback.

- [ ] **Step 4: Add responsive behavior**

Use a desktop result table and mobile stacked result cards. Keep progress, failures, and retry actions visible without body-level horizontal overflow.

### Task 4: QA and Commit

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Create: browser-rendered IMP-01/SCR-01 evidence images in the prototype root.

- [ ] **Step 1: Run production build**

Run: `npm.cmd run build`
Expected: Vite exits with code 0.

- [ ] **Step 2: Run browser interaction matrix**

Test wizard validation, task creation, completed/total progression, isolated retries, filters, bulk selection/actions, task restore, and return navigation. Check console errors.

- [ ] **Step 3: Run responsive QA**

Capture import, processing, partial-success, and mobile result states. Compare shell, typography, spacing, colors, icons, and operational density with the selected reference.

- [ ] **Step 4: Commit**

Update `design-qa.md`, run `git diff --check`, and commit only UX-03 files and evidence.
