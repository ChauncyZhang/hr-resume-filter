# UX10 Scheduling Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver interviewer-first scheduling with privacy-safe availability and a complete paginated Monday-to-Sunday calendar.

**Architecture:** Keep feedback code in `InterviewViews.jsx`, extract scheduling and calendar UI into focused components, and centralize local calendar arithmetic in a dependency-free date utility. Add a read-only availability endpoint backed by internal interviews through a provider interface; the browser treats provider failure as unknown and still relies on the existing authoritative conflict endpoint immediately before save.

**Tech Stack:** React 19, Vite, Node test runner, FastAPI, SQLAlchemy, pytest.

## Global Constraints

- Scheduling order is candidate/round/duration, interviewer availability, date/time, invitation confirmation.
- Busy details expose only `已有安排`; external availability failure must never be rendered as free.
- Week views run Monday through Sunday and load every API cursor for the selected range.
- Narrow screens show a date strip and one selected day.
- Preserve existing feedback behavior and do not change backend persistence schemas.

---

### Task 1: Date utilities and range pagination

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/interviewDateUtils.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/interviewDateUtils.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/interviewController.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/interviewController.test.js`

**Interfaces:**
- Produces: `buildWeekDays(reference)`, `moveWeek(reference, amount)`, `weekRange(reference)`, `listRange(filters)`, and `availability(filters)`.

- [ ] Write tests for seven-day Monday-first weeks, week navigation, complete cursor traversal, and encoded availability parameters.
- [ ] Run the focused Node tests and confirm missing exports fail.
- [ ] Implement the date utilities and controller methods.
- [ ] Re-run the focused Node tests.

### Task 2: Privacy-safe availability API

**Files:**
- Create: `server/app/interviews/availability.py`
- Modify: `server/app/interviews/api.py`
- Modify: `server/tests/test_interview_api.py`

**Interfaces:**
- Produces: `GET /api/v1/interview-availability?from=&to=&participant_ids=&timezone=&buffer=&exclude=` returning participant status and opaque busy ranges.

- [ ] Write API tests for privacy, range/buffer/exclude handling, authorization, and conservative provider failure.
- [ ] Run the focused pytest cases and confirm the route is absent.
- [ ] Implement an internal SQL-backed provider protocol and endpoint without event titles or candidate details.
- [ ] Re-run focused API tests.

### Task 3: Scheduling workspace and complete calendar

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ScheduleWorkspace.jsx`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewCalendar.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`
- Modify: focused frontend source/behavior tests.

**Interfaces:**
- `ScheduleWorkspace` consumes candidates, participant options, controller-backed availability/conflict/save callbacks, and never initializes a new interview time.
- `InterviewCalendar` consumes filter/action callbacks and loads all pages for its selected week.

- [ ] Write source/behavior tests for component extraction, no guessed time, four-step hierarchy, Monday-Sunday controls, and narrow-screen day selection.
- [ ] Run the focused tests and confirm the old implementation fails.
- [ ] Implement availability states `可排`, `冲突`, `缓冲不足`, and `无法确认`, using `已有安排` as the only busy label.
- [ ] Keep the final conflict check in the save path and block save on hard or unknown availability.
- [ ] Implement previous/next/today/date-picker navigation and mobile date-strip/single-day layout.
- [ ] Re-run frontend tests and build.

### Task 4: Final verification and commit

**Files:** All files above only.

- [ ] Run relevant frontend tests and `npm run build`.
- [ ] Run relevant server interview tests.
- [ ] Run `git diff --check`, inspect `git status` and the complete diff.
- [ ] Commit only the UX10 scheduling/calendar changes with an accurate message.
