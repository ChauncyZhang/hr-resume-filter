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

## UX-04 Candidate Review and Progression QA

### Evidence

- Functional specification: `../../recruiting-platform-ux-spec.md`, F-03, CAN-01, and CAN-02
- CAN-01 desktop: `candidate-list-1280x720.png`
- CAN-01 mobile: `candidate-list-390x844.png`
- CAN-02 desktop screening evidence: `candidate-detail-1280x720.png`
- CAN-02 mobile profile: `candidate-detail-390x844.png`

The candidate workspace reuses the existing navigation, compact operational typography, neutral surfaces, restrained blue actions, Lucide icons, and 5-6 px radii. CAN-01 uses a comparison table on desktop and stable record cards on mobile. CAN-02 keeps identity, current application, state, owner, and next action visible while separating rule evidence, LLM advice, and human judgment.

### UX-04 Interactions Tested

- Candidate navigation, keyword/position/stage/owner/score filters, clear action, row selection, and bulk actions
- Workbench, JOB-03, and SCR-01 entries route into the same candidate profile
- Profile, applications, screening evidence, interview feedback, and timeline tabs
- Masked contact display plus copy/download feedback
- Notes, tags, and human conclusion persistence
- Allowed-next-state mapping and timeline append after progression
- Rejection blocked until a reason is entered
- Simulated concurrent update shows the latest server state and recovery actions without silent overwrite
- Desktop 1280 and mobile 390 rendering with no body-level horizontal overflow

Browser console errors checked: none.

### UX-04 Comparison History

1. The initial desktop candidate table required horizontal scrolling at 1280 px and clipped the next-action column. Column constraints were tightened while preserving all comparison fields; the final table fits its panel.
2. The initial mobile card placed source in a 24 px grid track, causing character-by-character wrapping. Source and owner now occupy labeled metadata regions without page overflow.
3. The original prototype opened candidates in a separate lightweight drawer. All candidate entry points now share CAN-02, preserving one candidate record and one progression history.
4. Final browser pass found no remaining P0/P1/P2 issue across CAN-01 or CAN-02.

## UX-05 Interview and Feedback QA

### Evidence

- Functional specification: `../../recruiting-platform-ux-spec.md`, F-04, F-05, and INT-01 through INT-03
- INT-01 desktop list: `interview-list-1280x720.png`
- INT-01 desktop week calendar: `interview-calendar-1280x720.png`
- INT-01 mobile list: `interview-list-390x844.png`
- INT-02 desktop schedule: `interview-schedule-1280x720.png`
- INT-02 mobile schedule: `interview-schedule-390x844.png`
- INT-03 desktop feedback: `interview-feedback-1280x720.png`
- INT-03 mobile feedback: `interview-feedback-390x844.png`

The interview workflow reuses the existing shell, typography scale, blue action hierarchy, neutral surfaces, Lucide icons, and compact ATS density. INT-01 uses a comparison table and a five-day calendar on desktop, with stable record cards on mobile. INT-02 remains a full workspace form rather than a narrow modal. INT-03 keeps the feedback form in one reading column and moves lower-priority interview context to a secondary region.

### UX-05 Interactions Tested

- Interview navigation, keyword/date/status/scope filters, and list/calendar switching
- Calendar blocks include time, candidate, position, interviewer, and text status rather than color alone
- New scheduling and rescheduling across basic information, collaboration, and invitation steps
- Known hard conflict blocks continuation while preserving meeting link and interviewer selection
- Conflict recovery, invitation preview, calendar output, save, and versioned reschedule messaging
- Notification failure remains on the saved interview and supports independent retry
- Feedback rating dimensions, strengths, risks, conclusion, notes, and visible draft state
- Empty submit exposes seven required-field errors without clearing other input
- First simulated network failure preserves the full draft; retry submits successfully and enters read-only state
- Another interviewer's submitted feedback remains read-only and exposes no edit action
- Candidate interview summaries and timelines update from saved interview/feedback records
- Desktop 1280 and mobile 390 rendering with no body-level horizontal overflow

Browser console errors checked: none.

### UX-05 Comparison History

1. Initial scheduling QA confirmed that a selected interviewer already booked at the same time blocks progression and retains all entered collaboration data.
2. The seeded notification failure originally required re-creating the interview. It now exposes an isolated retry action and keeps the local schedule intact.
3. The first feedback submission intentionally fails once to verify draft retention. Successful retry originally left the old failure notice visible; the notice is now cleared when submission succeeds.
4. Mobile tables were converted to stable stacked records, while the week calendar uses contained horizontal paging and the feedback form keeps all required fields visible.
5. Final browser pass found no remaining P0/P1/P2 issue across INT-01, INT-02, or INT-03.

## Cross-page Typography and Interview Fix QA

- Reproduced the CAN-02 “面试与反馈” white screen and captured `ReferenceError: CalendarDays is not defined`; added the missing Lucide import and verified the tab renders its empty state and scheduling actions without console errors.
- Replaced the browser-native `input[type=time]` with explicit hour and minute selects. Hours are 08–21 and minutes are 00/15/30/45, removing browser-specific wheel gaps while preserving the existing `HH:mm` data format.
- Consolidated the prototype around the UI specification's six-level type scale: page title 24px, section title 18px, panel title 16px, body/control 14px, label 13px, and caption 12px.
- Removed every 9px, 10px, and 11px declaration. Desktop audit reports visible text at 12px or above and all text-bearing controls at 14px.
- Rechecked the workbench, CAN-02 interview tab, and INT-02 schedule form at 1280 desktop and 390 mobile. Body-level horizontal overflow: none. Browser console errors: none.

## UX-06 Talent Pool and Reactivation QA

### Evidence

- TAL-01 desktop list: `talent-pools-1280x720.png`
- TAL-01 mobile list: `talent-pools-390x844.png`
- TAL-02 desktop detail: `talent-detail-1280x720.png`
- TAL-02 mobile member detail: `talent-detail-390x844.png`
- F-06 desktop reactivation: `talent-reactivate-1280x720.png`
- F-06 mobile reactivation: `talent-reactivate-390x844.png`

### UX-06 Interactions Tested

- Group search, visibility filtering, summary metrics, and create-group validation
- Talent keyword search plus role, city, owner, and follow-up filters
- Member tags, owner, next-contact date, move/remove actions, and retention state
- “永久不再联系” confirmation remains disabled until a reason is supplied
- Reactivation only exposes authorized active positions and previews the new application
- An active same-position application blocks duplicate creation and links to the existing record
- Successful reactivation appends a new “新简历” application while preserving the original application
- Desktop 1280 and mobile 390 rendering with no body-level horizontal overflow

Browser console errors checked: none.

### UX-06 Comparison History

1. TAL-01 established four distinct group types: recruiting-team, position-restricted, and personal follow-up visibility.
2. TAL-02 search was verified against name and skill context, with historical positions and latest conclusions kept in the comparison table.
3. The duplicate-application test selected an already active AI 工程师 application. Creation was disabled until a different authorized position was selected.
4. Reactivating 李嘉明 to Java 后端工程师 added a second application dated 2026-07-12 and retained the original AI 工程师 application dated 2026-07-11.
5. Mobile drawers use the full 375 px content width inside a 390 px viewport; list, detail, and reactivation states remain overflow-free.

Final result: passed.

## UX-07 Reports and Settings QA

### Evidence

- REP-01 desktop overview: `report-overview-1280x720.png`
- REP-01 mobile overview: `report-overview-390x844.png`
- SET-01 desktop organization: `settings-organization-1280x720.png`
- SET-01 mobile organization: `settings-organization-390x844.png`
- SET-03 desktop AI settings: `settings-ai-1280x720.png`
- SET-03 mobile AI settings: `settings-ai-390x844.png`
- SET-04 desktop audit and retention: `settings-audit-1280x720.png`

### Interactions Tested

- Report time, position, department, and owner filters; applied-condition removal and clear-all recovery
- Funnel stage drill-down into the existing candidate list with position and stage filters preserved
- Loading, empty, module-error, retry, and interviewer no-permission report states
- Organization search/filter, user detail editing, and confirmation before expanding position visibility
- Protected in-use recruitment stages plus simulated template-save failure, retained draft, and retry
- Masked API key, Provider enablement confirmation, HTTP 404 connection failure, and successful retest
- Dirty AI settings expose continue editing, discard, and save-draft-and-leave choices; saved drafts restore on return
- Audit filtering, masked IP, Trace ID, detail drawer, and confirmation before shortening retention
- Administrator edit access, HR read-only access, and interviewer denial or interview-template-only access
- Desktop 1280 and mobile 390 rendering with no body-level horizontal overflow

Browser console errors checked: none. Domain tests, Vite build, and whitespace validation passed.

Final result: passed.

## Talent Resume Preview and Download QA

### Evidence

- User reference: `talent-resume-row-reference.png`
- Desktop preview: `talent-resume-preview-1280x720.png`
- Mobile preview: `talent-resume-preview-390x844.png`

The member header, summary, masked contact hierarchy, and compact typography remain consistent with the supplied reference. The former plain “当前简历” value now keeps the same row position while adding a linked filename and explicit preview/download actions. The preview drawer continues the existing right-side drawer language instead of introducing a separate route or browser window.

### Interactions Tested

- Linked filename and “预览” button open the same résumé preview drawer
- Two candidate-specific preview pages show profile, summary, skills, experience, and education
- Preview metadata exposes file type, page count, parse quality, and prototype status
- Download from the preview drawer triggers the “简历下载已开始” confirmation
- Closing preview preserves the underlying talent member drawer and its controls
- Desktop 1280px uses a 560px preview drawer with no body-level horizontal overflow
- Mobile 390px uses the full 375px content width with no body-level horizontal overflow

Browser console errors checked: none.

Final result: passed.
