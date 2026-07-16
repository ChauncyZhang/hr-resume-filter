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
