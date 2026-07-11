# Design QA

## Comparison Target

- Source visual truth: `reference-option-2.png` plus user refinement feedback to increase text size and slightly widen the right rail
- Implementation: `http://127.0.0.1:4174/`
- Browser-rendered desktop screenshot: `implementation-1440x1024-final.png`
- Browser-rendered mobile screenshot: `implementation-390x844-final.png`
- User feedback crops: `feedback-candidate-text.png`, `feedback-task-text.png`
- Viewport: 1440 × 1024 desktop; 390 × 844 mobile
- State: 工作台、AI 工程师、候选人看板默认状态

## Evidence

### Full-view comparison

The source and final desktop screenshot were opened together at equivalent desktop scale. The implementation preserves the fixed left navigation, compact top bar, job switcher, six-stage pipeline, right-side task rail, duplicate-candidate alert, and bottom refresh status. The user-requested 260 px task rail is intentionally wider than the generated source, improving readability without changing the page hierarchy.

### Focused region comparison

- Source crop: `qa-source-center.png`
- Implementation crop: `qa-implementation-center.png`
- Region: AI 工程师 pipeline header, six stage columns, candidate cards, stage counts, and load-more actions.

The final crop includes the same visible candidate count and card order as the source. Typography, neutral surface palette, borders, icon family, column rhythm, and compact card hierarchy are consistent. Minor rasterization differences are expected between the generated image and browser-rendered system fonts.

## Required Fidelity Surfaces

- Fonts and typography: Chinese system font stack, size hierarchy, line height, weight, and zero letter spacing are consistent with the source. Candidate and task-rail body text is now 12 px, with 11 px metadata, resolving the user's small/blurry-text feedback. Long role names truncate without changing column width.
- Spacing and layout rhythm: 178 px fixed navigation, compact header, six equal pipeline columns, 260 px right rail, 5–7 px radii, and low-elevation surfaces match the intended product structure. Desktop has no page overflow at 1440 × 1024.
- Colors and visual tokens: white surfaces, pale gray stage backgrounds, restrained blue primary actions, and semantic red/orange/blue status dots match the source direction. No gradients are used.
- Image quality and asset fidelity: the source contains no photographic or illustrative assets. All interface icons use the Lucide library; no custom SVG, emoji, CSS art, or placeholder illustration replaces a source asset.
- Copy and content: navigation, job names, stage names, candidate records, pending items, and calendar labels align with the source mock and use synthetic data.

## Interactions Tested

- Job selection and board/list view switch
- Candidate card → detail drawer → stage progression
- Resume import → file selection simulation → parsing → success
- Duplicate candidate processing dialog
- Urgent-item filter and refresh feedback
- Mobile navigation drawer at 390 × 844
- Keyboard focus styles and reduced-motion fallback present

Browser console errors checked: none.

## Comparison History

1. Initial comparison found a P2 vertical-density mismatch: the pipeline and task rail ended materially above the source, and three visible source candidates were missing.
2. Increased pipeline and task-rail height, adjusted footer spacing to remove desktop overflow, and added candidates B5, C5, and E5.
3. Re-captured the implementation at 1440 × 1024 and repeated full-view and focused-region comparison. Earlier density and content mismatches are resolved.
4. User review identified text that was too small and a narrow task rail. Candidate and task text was increased by 1–2 px, metadata contrast was strengthened, and the rail was widened from 220 px to 260 px. The revised desktop capture remains overflow-free and the mobile layout remains usable.
5. A second user review identified the candidate-card copy and right-rail task copy as still too small. Candidate names were raised to 14 px, role text to 13 px, and metadata to 12 px; task-group headings were raised to 14 px, task rows to 13 px, and supporting text to 12 px. Card and row spacing was rebalanced so the 1440 × 1024 desktop remains overflow-free.

## Findings

No actionable P0, P1, or P2 differences remain. The final implementation is suitable as a low-fidelity UX-01/UX-02 prototype rather than a production visual specification.

## UX-02 Position Flow QA

### Evidence

- Visual language source: `reference-option-2.png`
- Functional specification: `../../recruiting-platform-ux-spec.md`, UX-02 and pages JOB-01/JOB-02/JOB-03
- JOB-01 desktop: `job-list-1440x1024.png`
- JOB-01 mobile: `job-list-390x844.png`
- JOB-02 desktop: `job-form-1440x1024.png`
- JOB-03 desktop: `job-detail-1280x720.png`
- JOB-03 mobile: `job-detail-390x844.png`

The reference workbench and the three position screens were opened together. The position flow reuses the selected shell, typography scale, blue action color, neutral surfaces, 5–6 px radii, Lucide icon style, and dense operational layout. JOB-01 uses a desktop data table and mobile record cards; JOB-02 uses segmented form sections with a sticky completion summary; JOB-03 uses compact metrics, tabs, a funnel strip, and candidate records.

### UX-02 Interactions Tested

- Position navigation from the global sidebar
- Keyword, status, department, and owner filtering
- Position list → detail → edit → list navigation
- Required-field validation for position name and public JD
- AI criterion extraction loading and success states
- Unsaved-form continue/edit, discard, and save-draft dialog
- Publish position and return to its detail view
- Pause and restore recruiting
- Candidate, position information, collaboration activity, and settings tabs
- Resume import entry from position detail
- New position zero-candidate funnel and empty state
- Scroll restoration when moving from a scrolled list to position detail
- Desktop widths at 1440 and 1280; mobile width at 390

Browser console errors checked: none. Desktop body-level horizontal overflow: none at 1440. Mobile body-level horizontal overflow: none at 390; funnel uses intentional contained horizontal scrolling.

### UX-02 Comparison History

1. Initial JOB-01 implementation duplicated the primary “新建职位” action in the top bar and page heading. The page-level duplicate was removed, leaving one context-aware primary action.
2. Initial mobile JOB-03 retained the list scroll position and used a wide candidate table. Added route-state scroll restoration and converted mobile candidate rows into stacked cards.
3. Initial newly published positions incorrectly displayed the AI 工程师 sample funnel and candidates. Added zeroed funnel counts and an explicit empty state for positions without candidates; the workbench now also uses empty stages for unknown positions.
4. Non-AI positions initially reused AI candidate backgrounds. Added position-specific synthetic profiles for Java, product, frontend, and recruiting operations roles.
5. Final browser pass found no remaining P0/P1/P2 issue across JOB-01, JOB-02, or JOB-03.

## Follow-up Polish

- P3: Browser text antialiasing is slightly sharper than the generated source image; retain native rendering for accessibility and implementation realism.

## UX-03 Import and Screening QA

### Evidence

- Visual language source: `reference-option-2.png`
- Functional specification: `../../recruiting-platform-ux-spec.md`, F-02, IMP-01, and SCR-01
- IMP-01 desktop validation state: `import-wizard-1280x720.png`
- IMP-01 mobile start state: `import-wizard-390x844.png`
- SCR-01 desktop processing state: `screening-progress-1280x720.png`
- SCR-01 desktop partial-success state: `screening-partial-1280x720.png`
- SCR-01 mobile completed state: `screening-task-390x844.png`

The workbench reference and UX-03 screens were opened together. The import wizard and task page reuse the same shell, Chinese system typography, restrained blue actions, neutral operational surfaces, semantic status colors, Lucide icons, and compact table density. No photographic or illustrative asset is required by these flows.

### UX-03 Interactions Tested

- Workbench and JOB-03 import entry points
- Three-step batch information, file validation, and confirmation flow
- Unsupported ZIP file blocks task creation until removed
- Current filename, current stage, and completed/total progress from 0/5 to 5/5
- Independent parse failure and LLM partial-success states
- Human-readable error, secondary trace ID, parse retry, and LLM retry
- Rule score remains available when LLM evaluation fails
- All/processing/success/partial/failed result filters and keyword search
- Completed-row selection, bulk advance, and short-lived undo
- Recent task persistence and restore through task ID snapshot
- Desktop 1280 and mobile 390 rendering with no body-level horizontal overflow

Browser console errors checked: none.

### UX-03 Comparison History

1. Initial IMP-01 test exposed an unsupported ZIP file alongside valid resumes. Creation remained blocked until the invalid file was removed; valid files and batch metadata were preserved.
2. Initial processing rows revealed their eventual scores before completion. Queued rows now show “等待处理” and blank rule/LLM scores until the file finishes.
3. The deterministic task produced one parse failure and one LLM partial success without blocking the other three resumes. Isolated retries converted both rows to success and the task to complete.
4. Mobile SCR-01 initially inherited the desktop result table. It now uses stacked result cards while keeping filters, progress, separate scores, evidence, risks, and actions readable.
5. Final browser pass found no remaining P0/P1/P2 issue across IMP-01 or SCR-01.

final result: passed
