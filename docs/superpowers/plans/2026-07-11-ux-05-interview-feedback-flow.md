# UX-05 Interview and Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build INT-01 through INT-03 so HR can manage interview schedules and interviewers can submit structured feedback in under three minutes.

**Architecture:** Add an interview-domain React module with shared in-memory interview records and three modes: interview list/calendar, schedule/reschedule form, and feedback form. `App.jsx` owns interview records and routes global interview navigation plus candidate-detail entry points into the same workflow; successful feedback updates the interview record and candidate timeline.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, browser interaction QA.

## Global Constraints

- Reuse the current shell, typography, colors, radii, button hierarchy, and responsive breakpoints.
- HR defaults to interview list and can switch to week calendar; mobile uses the list as the primary view.
- Calendar status uses text and icons in addition to color.
- Scheduling is a full workspace form, not a narrow modal.
- Preserve all scheduling input when a conflict is found.
- Notification failure does not delete a saved interview.
- Feedback uses one narrow column, visibly auto-saves a draft, and retains input after validation or network failure.
- Interviewers only see the candidate materials required for their assigned interview.
- Use synthetic candidates and masked contact information.

---

### Task 1: INT-01 Interview List and Week Calendar

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: `records`, `onSchedule(record?)`, `onFeedback(record)`, and `onNotify(message)`.
- Produces: selected interview, scope/status filters, list/calendar preference, and interview actions.

- [x] **Step 1: Define interview records and statuses**

Create synthetic scheduled, completed, pending-feedback, cancelled, and notification-failed records with candidate, position, round, method, time, duration, interviewer, location/link, notification state, and feedback state.

- [x] **Step 2: Build list controls and table**

Implement keyword, date, status, and interviewer-scope filters; show candidate, position/round, time/method, interviewers, status, notification, and next action.

- [x] **Step 3: Build week calendar**

Render five stable day columns with timed interview blocks. Each block must include time, candidate, position, interviewer, and text status; selecting a block opens its contextual action.

- [x] **Step 4: Add loading, empty, error, and permission states**

Provide compact contained states and a “仅看我的面试” scope that does not expose unrelated candidate summaries.

### Task 2: INT-02 Schedule and Reschedule Interview

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: candidate/application context, optional existing interview, and `onSave(interview)`.
- Produces: created or versioned rescheduled record, conflict decision, invitation text, and notification state.

- [x] **Step 1: Build the three-step schedule form**

Step 1 confirms candidate, position, round, method, timezone, date, start time, and duration. Step 2 selects interviewers and location/link. Step 3 previews candidate/interviewer invitation text and calendar output.

- [x] **Step 2: Validate required scheduling fields**

Keep all values and focus the first invalid field when candidate, time, interviewer, or location/link is missing.

- [x] **Step 3: Detect known conflicts**

Show a blocking hard conflict for the same interviewer at the same time and a soft conflict for tight adjacent meetings. Allow time adjustment or explicit soft-conflict override without clearing the form.

- [x] **Step 4: Save, reschedule, and recover notification failure**

Append a change record when rescheduling, invalidate the prior calendar version, generate invitation text, and expose copy/download/retry actions when the simulated notification channel fails.

### Task 3: INT-03 Interview Feedback

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: assigned interview and candidate summary.
- Produces: private draft, submitted structured feedback, interview completion state, and candidate timeline event.

- [x] **Step 1: Build the restricted material summary**

Keep candidate, position, round, JD priorities, masked résumé summary, and suggested questions visible without exposing unrelated applications or contact data.

- [x] **Step 2: Build the single-column feedback form**

Use compact segmented ratings for professional ability, problem solving, communication, and role fit; collect strengths, risks, conclusion, and optional notes.

- [x] **Step 3: Add draft and validation behavior**

Display “保存中/已保存” transitions, preserve values across tabs, and block submit while focusing the first missing required field.

- [x] **Step 4: Add submit, read-only, and edit-reason states**

Submitted feedback becomes read-only and identifies the next HR owner. Editing submitted feedback requires a reason and appends an audit entry; another interviewer’s feedback remains non-editable.

### Task 4: Entry Integration, QA, and Commit

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Create: INT-01/INT-02/INT-03 desktop and mobile evidence images.

**Interfaces:**
- Consumes: candidate and interview state from Tasks 1-3.
- Produces: one navigable UX-05 prototype with documented QA evidence.

- [x] **Step 1: Unify interview entry points**

Route the global interview navigation, workbench “待安排/待反馈” items, and CAN-02 interview tab to INT-01, INT-02, or INT-03 while preserving return context.

- [x] **Step 2: Run the interaction matrix**

Test list/calendar switching, filters, schedule validation, hard/soft conflicts, save, reschedule, notification retry, feedback draft, required fields, submit, read-only state, and return navigation.

- [x] **Step 3: Run responsive and console QA**

Capture representative INT-01, INT-02, and INT-03 states at desktop 1280 and mobile 390; verify no body-level horizontal overflow and no console errors.

- [x] **Step 4: Build and commit**

Run `npm run build` and `git diff --check`, update QA evidence, and commit only UX-05 files.
