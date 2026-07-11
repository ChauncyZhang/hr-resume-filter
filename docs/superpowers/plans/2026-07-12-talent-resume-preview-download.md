# Talent Resume Preview and Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current résumé in talent member details previewable and downloadable without leaving the talent-pool workflow.

**Architecture:** Add pure résumé document helpers in a focused module so generated preview/download content is testable with Node's built-in test runner. `TalentPoolViews.jsx` adds file actions and a stacked preview drawer while continuing to own only UI state; `App.jsx` supplies the existing notification callback.

**Tech Stack:** React 19, Vite 6, Lucide React, CSS, Node `node:test`, browser interaction QA.

## Global Constraints

- Preserve the existing 24/18/16/14/13/12px typography scale and ATS visual language.
- Do not add a route, PDF library, backend API, or real candidate file.
- Desktop preview drawer width is 560px; mobile width is the full 375px content area at a 390px viewport.
- Closing preview must preserve the member drawer and its current state.
- Download content must be UTF-8 and derived from the selected candidate.

---

### Task 1: Testable Résumé Document Helpers

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/resumeDocument.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/resumeDocument.test.js`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/package.json`

**Interfaces:**
- Consumes: candidate records containing `name`, `role`, `company`, `city`, `phone`, `email`, `summary`, `skills`, `experience`, and `education`.
- Produces: `buildResumeDocument(candidate)` returning `{ fileName, mimeType, pages, downloadText }`.

- [x] **Step 1: Write failing helper tests**

Assert that `buildResumeDocument(candidate)` returns `{name}_简历.txt`, two candidate-specific preview pages, UTF-8 plain-text MIME metadata, and download text containing the candidate's summary, skills, experience, and education.

- [x] **Step 2: Run tests and confirm RED**

Run: `npm test`
Expected: FAIL because `resumeDocument.js` does not exist.

- [x] **Step 3: Implement the minimal helper**

Create the stable document object using only candidate fields and no browser APIs.

- [x] **Step 4: Run tests and confirm GREEN**

Run: `npm test`
Expected: all résumé document tests pass.

### Task 2: File Actions and Preview Drawer

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Consumes: `buildResumeDocument(candidate)` and `onNotify(message)`.
- Produces: `ResumeFileActions`, `ResumePreviewDrawer`, preview open/close state, and browser Blob download behavior.

- [x] **Step 1: Add file actions**

Replace the plain current-résumé value with a file row containing a clickable filename plus Lucide preview and download buttons.

- [x] **Step 2: Add the stacked preview drawer**

Render metadata and two scrollable preview pages above the retained member drawer. Support close from header/footer without resetting member state.

- [x] **Step 3: Add download behavior**

Create an object URL from `downloadText`, trigger an anchor download, revoke the URL, and send success/failure through `onNotify`.

- [x] **Step 4: Add responsive styles**

Keep file actions readable at desktop width and stack controls at 390px without body-level horizontal overflow.

### Task 3: Browser QA, Documentation, and Commit

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Create: `docs/design/prototypes/ats-low-fi-option-2/talent-resume-preview-1280x720.png`
- Create: `docs/design/prototypes/ats-low-fi-option-2/talent-resume-preview-390x844.png`

**Interfaces:**
- Consumes: the completed talent résumé flow.
- Produces: verified interaction evidence and a focused commit.

- [x] **Step 1: Verify desktop interactions**

Open a talent member, launch preview from filename and preview button, verify two pages and download action, then close and confirm the member drawer remains.

- [x] **Step 2: Verify mobile layout**

At 390x844, verify 375px drawer width, visible file controls, full-width preview drawer, and no body-level horizontal overflow.

- [x] **Step 3: Run final checks**

Run: `npm test`, `npm run build`, and `git diff --check`.
Expected: all commands pass and browser console has no errors.

- [x] **Step 4: Commit**

Commit message: `Add talent resume preview and download`.
