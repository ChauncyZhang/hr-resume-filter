# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Durable product rules from HR usability review:

- Any control that visually suggests clickability must open a complete destination or action; do not ship decorative chevrons, rows, or buttons.
- Organization-owned entities such as departments and workflow templates need a discoverable management entry near every selector that consumes them.
- New users enter through an invitation and self-service password setup flow. Administrators must not invent, retain, or later reveal user passwords.
- Keep organization-level configuration separate from job-level choices: settings define workflow templates and AI availability; a job only selects a template and opts into an available AI evaluation.
- Do not ask non-technical HR users to type internal identifiers or free-form names for managed entities when a configured selector can be provided.
- Open transient read-only document previews, such as a candidate resume, in a large centered modal with a backdrop; render the authorized original file in the document reader instead of presenting parsed text as a PDF, and reserve right-side drawers for editable contextual details.
- Operational batch workflows such as resume screening need a discoverable primary navigation entry and a server-backed task list; do not make an import dialog the only way to resume a task.
- Cross-module links must encode an explicit in-app return target when the user is expected to continue the originating workflow. Do not depend only on component memory or browser history for returning from candidate, interview, or settings details.
- Keep each page-level primary action in the shared topbar action slot; do not position equivalent actions inside page-specific content headers.
- Board and list density changes must preserve visible, clickable candidate records; never hide operational data to make stage columns fit.
- Binary settings controls must keep compact checkbox or toggle dimensions and align with their labels and related actions; generic text-input sizing must never stretch them.
- Role hierarchy must be reflected in assignment selectors: recruiting administrators can be selected anywhere a hiring manager or interviewer is eligible to act.
- Organization entities use reversible lifecycle management. A disabled department remains visible for historical records but cannot receive new members or jobs until re-enabled.
- Interview workflow templates provide the recommended next round, not a hard ceiling. After configured rounds are complete, authorized HR users must still be able to add another interview; scheduling that interview automatically returns the application from decision to interviewing.
- Keep process stages, actionable tasks, AI routing conclusions, and notification read state semantically separate. User-facing stage labels must identify the responsible actor or business outcome; internal API and database state values may remain stable behind a shared display mapping.
- Candidate deletion remains blocked by default while applications are active. System administrators must see the active application count and explicitly confirm terminating those applications in a second destructive-action dialog; the server performs termination and approval atomically and records the count in the audit trail.
