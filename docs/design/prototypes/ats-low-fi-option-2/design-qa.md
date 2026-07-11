# Design QA

## Comparison Target

- Source visual truth: `reference-option-2.png` plus user refinement feedback to increase text size and slightly widen the right rail
- Implementation: `http://127.0.0.1:4174/`
- Browser-rendered desktop screenshot: `implementation-1440x1024-final.png`
- Browser-rendered mobile screenshot: `implementation-390x844-final.png`
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

## Findings

No actionable P0, P1, or P2 differences remain. The final implementation is suitable as a low-fidelity UX-01 prototype rather than a production visual specification.

## Follow-up Polish

- P3: Browser text antialiasing is slightly sharper than the generated source image; retain native rendering for accessibility and implementation realism.

final result: passed
