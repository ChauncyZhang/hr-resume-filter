# UX-08 Integration and Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver UX-08A and UX-08B together by generating a privacy-safe synthetic resume pack, making F-01 through F-06 share consistent workflow state, and completing documented expert usability tests for administrator, HR, and interviewer roles.

**Architecture:** Keep `App.jsx` as the prototype state owner and move cross-module business updates into `ux08Workflow.js` pure functions. Screening, interviews, talent pools, positions, candidates, and reports consume the same updated records. A development-only scenario switch restores deterministic test starting states, while Markdown test artifacts and browser evidence record UX-08B results without claiming real-user research.

**Tech Stack:** React 19, Vite 6, Lucide React, Node `node:test`, bundled Python with `python-docx`/ReportLab/Pillow, Poppler/LibreOffice rendering, in-app browser QA.

## Global Constraints

- Use only synthetic personal data; email domains must be `example.com` and no real phone numbers, addresses, photos, employers, or schools may appear.
- Preserve the existing ATS shell and 24/18/16/14/13/12px typography scale.
- Do not add real backend, LLM, email, calendar, recruitment-channel, Offer, onboarding, or multi-tenant integration.
- F-01 through F-06 must work without page refresh or manual data repair.
- Desktop acceptance viewport is 1280×720; mobile acceptance viewport is 390×844.
- P0 and P1 issue counts must be zero before completion.

---

### Task 1: Synthetic Resume Pack

**Files:**
- Create: `scripts/generate_ux08_resumes.py`
- Create: `docs/design/test-data/ux-08-resumes/README.md`
- Create: `docs/design/test-data/ux-08-resumes/manifest.json`
- Create: `docs/design/test-data/ux-08-resumes/expected-results.csv`
- Create: 18 fixture files under `docs/design/test-data/ux-08-resumes/files/`

**Interfaces:**
- Consumes: deterministic fixture definitions embedded in the generator.
- Produces: 18 synthetic files plus manifest records with `id`, `filename`, `format`, `targetPosition`, `expectedParseStatus`, `expectedScoreRange`, `scenarioTags`, and `synthetic: true`.

- [x] **Step 1: Write fixture definitions and verification mode**

Add a deterministic `FIXTURES` list and `verify_output(output_dir)` that asserts 18 unique IDs/files, allowed domains, required role distribution, duplicate/same-name scenarios, and no unmasked phone number pattern.

```python
def verify_output(output_dir: Path) -> None:
    manifest = json.loads((output_dir / "manifest.json").read_text("utf-8"))
    assert len(manifest) == 18
    assert all(item["synthetic"] is True for item in manifest)
    assert Counter(item["targetPosition"] for item in manifest) == {
        "AI 工程师": 8,
        "Java 后端工程师": 4,
        "产品经理": 3,
        "前端工程师": 3,
    }
```

- [x] **Step 2: Run verification and confirm RED**

Run: bundled Python `scripts/generate_ux08_resumes.py --verify-only`.

Expected: non-zero exit because the output pack does not exist.

- [x] **Step 3: Generate TXT, DOCX, text PDF, scan-like PDF, long, and corrupt fixtures**

Use `python-docx` for DOCX, ReportLab for text PDF, and Pillow + ReportLab for image-only PDF. The corrupt PDF is intentionally invalid and must be marked `expectedParseStatus: failed`.

- [x] **Step 4: Render and inspect representative files**

Render at least one DOCX, one text PDF, one scan-like PDF, and the long fixture. Inspect every rendered page for readable Chinese text, clipping, overlap, and correct synthetic labels.

- [x] **Step 5: Run fixture verification**

Run: bundled Python `scripts/generate_ux08_resumes.py --verify-only`.

Expected: `18 synthetic resumes verified`.

### Task 2: Shared Workflow Domain

**Files:**
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ux08Workflow.js`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/ux08Workflow.test.js`

**Interfaces:**
- Consumes: `{ positions, candidates, interviews, pools, memberships }` and workflow commands.
- Produces: `applyScreeningResults`, `transitionCandidate`, `saveInterview`, `submitInterviewFeedback`, `addTalentMemberships`, `reactivateTalentCandidate`, `recalculatePositionCounts`, and `validateWorkflowState`.

- [x] **Step 1: Write failing workflow tests**

Cover these invariants:

```js
test("screening results create one candidate per successful file", () => {});
test("scheduling moves a candidate to interview and updates position counts", () => {});
test("submitted feedback moves the candidate to decision", () => {});
test("talent membership preserves the original application", () => {});
test("reactivation creates a linked application and blocks an active duplicate", () => {});
test("validator reports no dangling interview or membership references", () => {});
```

- [x] **Step 2: Run `npm test` and confirm RED**

Expected: failure because `ux08Workflow.js` does not exist.

- [x] **Step 3: Implement minimal immutable helpers**

Each helper returns a new state object and never mutates input arrays. Candidate stages must remain one of `新简历 | 待复核 | 待沟通 | 待安排 | 面试中 | 待决策 | 已录用 | 已淘汰 | 已撤回`.

- [x] **Step 4: Run `npm test` and confirm GREEN**

Expected: existing tests and all UX-08 workflow tests pass.

### Task 3: Screening-to-Candidate Integration

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/ScreeningViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/syntheticResumeFixtures.js`

**Interfaces:**
- `ImportWizard` adds `onSelectFiles(files)` behavior for real local files and a deterministic synthetic sample action.
- `ScreeningTaskView` adds `onApplyResults({ action, files, task })`.
- `App.jsx` applies successful/partial results through `applyScreeningResults` and updates candidates and position counts together.

- [x] **Step 1: Add synthetic fixture metadata to the prototype**

Export the same stable candidate IDs, filenames, positions, expected scores, and failure types used by `manifest.json`.

- [x] **Step 2: Add actual file selection and synthetic sample loading**

The dropzone must expose an accessible file input accepting `.pdf,.docx,.txt`. A separate `载入 UX-08 合成样本` action loads deterministic fixtures without a system picker.

- [x] **Step 3: Make screening bulk actions update shared state**

`推进到待复核` creates or updates candidates, appends a screening timeline event, and updates the target position counters. `加入人才库` first creates missing candidates, then creates memberships.

- [x] **Step 4: Preserve screening origin and return paths**

Opening a candidate from a screening result and returning must restore the same task, filter state, and selected position.

- [x] **Step 5: Run targeted tests and build**

Run: `npm test` and `npm run build`.

Expected: all tests pass and Vite builds without warnings that affect behavior.

### Task 4: Interview, Talent, Report, and Scenario Integration

**Files:**
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/App.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/InterviewViews.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/TalentPoolViews.jsx`
- Create: `docs/design/prototypes/ats-low-fi-option-2/src/Ux08ScenarioPanel.jsx`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/src/styles.css`

**Interfaces:**
- Interview save and feedback submit use the Task 2 helpers.
- Talent add/reactivate use the Task 2 helpers and return explicit duplicate outcomes.
- `Ux08ScenarioPanel` consumes `currentScenario`, `validation`, `onSelect`, and `onReset`.

- [x] **Step 1: Synchronize scheduling and feedback**

Saving an interview moves the candidate to `面试中`, appends timeline data, and updates counters. Submitting feedback moves the candidate to `待决策` and makes the result visible from candidate detail.

- [x] **Step 2: Synchronize talent membership and reactivation**

Adding a member preserves prior applications. Reactivation creates a linked `新简历` application and keeps duplicate creation disabled when an active same-position application exists.

- [x] **Step 3: Add a development-only scenario panel**

Show a compact `验收场景` control only when `import.meta.env.DEV`. Switching scenarios requires confirmation and restores deterministic data for default, partial screening, pending feedback, talent reactivation, empty, and restricted states.

- [x] **Step 4: Expose workflow validation**

The scenario panel displays `数据一致` only when `validateWorkflowState` returns no errors; otherwise it lists the first error and provides reset.

- [x] **Step 5: Verify report drill-down after state changes**

After screening, scheduling, feedback, and reactivation, report totals and funnel stages must match candidate records and drill down to the same records.

### Task 5: UX-08B Test Package and Browser Audit

**Files:**
- Create: `docs/design/ux-08-usability-test-script.md`
- Create: `docs/design/ux-08-expert-test-results.md`
- Create: `docs/design/ux-08-issue-log.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/README.md`
- Modify: `docs/design/prototypes/ats-low-fi-option-2/design-qa.md`
- Create: UX-08 evidence screenshots under `docs/design/prototypes/ats-low-fi-option-2/ux-08-evidence/`

**Interfaces:**
- Consumes: the integrated prototype and synthetic resume pack.
- Produces: 12 expert task records, a real-user test kit, issue log, and desktop/mobile evidence.

- [x] **Step 1: Write the real-user test kit**

Include privacy instructions, role cards, 12 task cards, observer fields, five-point task difficulty, completion time, failure reason, and final feedback. State that only bundled synthetic resumes may be used.

- [ ] **Step 2: Execute six end-to-end flows in the in-app browser**

Capture accepted evidence for F-01 through F-06. For each action, use a fresh DOM snapshot before interaction and inspect every saved screenshot.

- [ ] **Step 3: Execute role, error, and recovery tasks**

Test administrator, HR, and interviewer boundaries; partial screening retry; notification failure retention; feedback draft retry; permission expansion; AI dirty-state recovery; and retention shortening confirmation.

- [ ] **Step 4: Verify responsive and keyboard behavior**

At 1280×720 and 390×844, verify body-level horizontal overflow is absent. Check navigation, dialogs, drawers, tables/cards, focus visibility, and text containment.

- [ ] **Step 5: Record and fix findings**

Every finding receives an ID, severity, evidence, expected behavior, actual behavior, fix, and retest result. Do not close P2 without a fix or explicit accepted-risk reason.

- [x] **Step 6: Run final gates**

Run:

```powershell
npm test
npm run build
git diff --check
```

Expected: all pass; issue log reports `P0=0`, `P1=0`.

- [x] **Step 7: Commit and integrate**

Commit with `Add UX-08 integrated usability workflow`, merge to `main`, rerun tests/build, and remove the temporary worktree.
