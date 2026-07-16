# UX-10 Browser Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make browser URLs the single source of page state across the recruiting application, including reliable back/forward, deep links, filters, tabs, and job-create draft recovery.

**Architecture:** Add a pure `appRouter.js` boundary for route parsing/building, safe in-app back behavior, URL query normalization, and session-scoped job draft persistence. `App.jsx` consumes React Router location/navigation and derives all page modes from the parsed route; view components receive only the controlled tab/filter/draft interfaces they need.

**Tech Stack:** React 19, react-router-dom 7, Vite 6, Node test runner.

## Global Constraints

- Use standard `BrowserRouter`; URL is the page source of truth.
- Cover workbench, jobs list/new/detail/edit, candidates list/detail, interviews list/new/reschedule/feedback, talent, reports, and every settings tab.
- Preserve a new-job draft while visiting department management; clear it on save, discard, and logout.
- Put candidate detail tab and list query, job, stage, owner, and minimum-score filters in the URL.
- Do not change backend APIs, CSS, or `InterviewViews.jsx`.
- Verify production nginx keeps `try_files $uri $uri/ /index.html`.

---

### Task 1: Pure route and draft contract

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/appRouter.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/appRouter.test.js`
- Delete: `docs/design/prototypes/ats-low-fi-option-2/src/appHistory.js`
- Delete: `docs/design/prototypes/ats-low-fi-option-2/src/appHistory.test.js`

**Interfaces:**
- Produces: `parseAppRoute(location)`, `routeForNav(label)`, `candidateListPath(filters)`, `candidateDetailPath(candidate, tab)`, `settingsPath(section, tab, returnTo)`, `safeNavigateBack(navigate, fallback, historyState)`, and job draft read/write/clear helpers.

- [ ] Write table-driven failing tests for every required path, candidate query normalization, settings tabs, safe fallback back, and draft lifecycle.
- [ ] Run `npm test -- src/appRouter.test.js`; expect module-not-found failure.
- [ ] Implement the minimal pure route and draft module and remove callback-stack history.
- [ ] Run `npm test -- src/appRouter.test.js`; expect all new tests to pass.

### Task 2: BrowserRouter application shell

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/package.json`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/package-lock.json`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/main.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ShellNavigation.test.js`

**Interfaces:**
- Consumes: Task 1 route builders/parser and draft helpers.
- Produces: URL-derived navigation/modes and route-aware callbacks passed to workspaces.

- [ ] Add failing source-contract assertions for BrowserRouter, route-derived shell state, route coverage, safe page-back calls, and logout draft clearing.
- [ ] Run `npm test -- src/ShellNavigation.test.js`; expect the new assertions to fail.
- [ ] Install `react-router-dom`, wrap the app in `BrowserRouter`, derive active module and modes from `useLocation`, and replace all page state transitions with `navigate` calls.
- [ ] Resolve deep-linked entity IDs after data loads and redirect unknown/forbidden paths to the role default with `replace`.
- [ ] Run `npm test -- src/ShellNavigation.test.js src/appRouter.test.js`; expect pass.

### Task 3: Controlled job, candidate, and settings route state

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/JobViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/CandidateViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/SettingsViews.jsx`
- Modify: focused existing `*.test.js` contract tests beside those views.

**Interfaces:**
- Consumes: route state/callback props from Task 2.
- Produces: controlled new-job draft, candidate filters/detail tab, and settings section/subtab behavior.

- [ ] Add failing assertions that the job form reports every draft change and distinguishes discard/save, candidate filters and detail tabs call URL callbacks, and settings section/subtabs are controlled.
- [ ] Run the focused Node tests; expect failures for missing props/contracts.
- [ ] Thread the smallest controlled props through each workspace without visual or backend changes.
- [ ] Ensure department management includes a URL return target and renders a return-to-draft action in the shell.
- [ ] Run focused tests; expect pass.

### Task 4: Full verification and commit

**Files:**
- Verify: `deploy/nginx/default.conf`
- Verify: `deploy/nginx/production.conf.template`
- Verify: all changed frontend files.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: a verified commit on `feature/ux10-router`.

- [ ] Run `npm test` in the prototype directory; expect zero failures.
- [ ] Run `npm run build`; expect Vite exit code 0.
- [ ] Run the production topology nginx fallback test or, if its dependencies are unavailable, verify both committed configs contain the exact fallback directive and report the limitation.
- [ ] Run `git diff --check`; expect no output.
- [ ] Review `git status --short` and `git diff --stat` for scope.
- [ ] Commit all intentional changes with `feat: add reliable browser routing` and report the hash and checks.
