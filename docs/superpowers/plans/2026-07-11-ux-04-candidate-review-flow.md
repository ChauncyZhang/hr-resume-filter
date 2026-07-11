# UX-04 Candidate Review and Progression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cross-position candidate list and full candidate review flow for CAN-01, CAN-02, and F-03.

**Architecture:** Add `CandidateViews.jsx` with candidate-domain mock data, list filters, detail tabs, notes, tags, and state transitions. `App.jsx` owns the selected candidate and routes workbench, position, screening, and candidate navigation entries into the same CAN-02 view. State remains in-memory for the prototype.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, browser interaction QA.

## Global Constraints

- Use a comparison-oriented table for CAN-01, not a card waterfall.
- Keep name, current application, current state, owner, and next action visible in CAN-02.
- Keep rule, LLM, and human conclusions separate and labeled with source/time.
- Show only allowed next states;淘汰 requires a reason.
- Preserve the selected row context and add each state change to the timeline.
- Use synthetic data and masked contact information.
- Validate desktop 1280/1440 and mobile 390 layouts.

---

### Task 1: CAN-01 Candidate List

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: candidate records, `onOpen(candidate)`, and `onNotify(message)`.
- Produces: filtered IDs and bulk-action state while preserving the current filters.

- [x] **Step 1: Add candidate records**

Define candidates across AI, Java, product, and frontend positions with source, owner, state, score, city, latest activity, masked phone/email, tags, and screening evidence.

- [x] **Step 2: Build list filters and table**

Add keyword, position, state, owner, minimum score, and clear actions. Show name, application, state, score, source, owner, latest activity, and next action.

- [x] **Step 3: Build selection and bulk actions**

Allow selecting visible non-terminal candidates, adding tags, assigning an owner, advancing to review, adding to talent pool, and showing an affected-count confirmation.

- [x] **Step 4: Add empty and mobile states**

Distinguish no candidates from no filter matches. Convert mobile rows into stable comparison cards without body-level horizontal overflow.

### Task 2: CAN-02 Candidate Detail

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: selected candidate and `onUpdate(candidate)`.
- Produces: updated notes, tags, human conclusion, application state, and timeline records.

- [x] **Step 1: Build fixed candidate summary**

Show name, role, masked contacts, city, source, current position, state, owner, latest activity, and next action with copy/download feedback.

- [x] **Step 2: Build detail tabs**

Implement résumé/profile, applications, screening evidence, interviews/feedback, and timeline tabs. Label AI evidence with provider/source and time.

- [x] **Step 3: Build notes and tags**

Allow adding a note and skill/process tags. Append notes to the activity timeline and keep them after tab changes.

- [x] **Step 4: Build human conclusion**

Record “建议推进、需要补充、暂不合适” plus an optional reason without deleting rule or LLM evidence.

### Task 3: Controlled State Progression

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`

**Interfaces:**
- Consumes: candidate current state and version.
- Produces: an allowed next state, required reason when applicable, incremented version, and timeline event.

- [x] **Step 1: Define allowed transitions**

Implement explicit allowed-next-state mapping for new résumé, review, communication, interview scheduling, interviewing, decision, hired, rejected, and withdrawn states.

- [x] **Step 2: Build progression dialog**

Show current state, allowed destination states, owner, reason field, and impact. Block rejection without a reason.

- [x] **Step 3: Simulate a concurrent update**

Provide a conflict state showing the latest server state and actions to refresh or reapply the intended change. Never silently overwrite.

- [x] **Step 4: Verify timeline integrity**

After transition, keep the user on the candidate, update the summary and next action, and append operator, old/new state, time, and reason.

### Task 4: Entry Integration, QA, and Commit

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Create: CAN-01/CAN-02 desktop and mobile browser evidence images.

- [x] **Step 1: Unify candidate entry points**

Route workbench cards, JOB-03 candidate rows, SCR-01 result rows, and the global candidate navigation to the same CAN-02 implementation.

- [x] **Step 2: Run browser interaction matrix**

Test filters, selection, all detail tabs, note/tag creation, human conclusion, valid transition, rejection validation, conflict recovery, and return navigation.

- [x] **Step 3: Run responsive and console QA**

Capture CAN-01 and CAN-02 at desktop and mobile widths, compare against the selected visual language, and check console errors.

- [x] **Step 4: Build and commit**

Run `npm.cmd run build`, `git diff --check`, update QA evidence, and commit only UX-04 files.
