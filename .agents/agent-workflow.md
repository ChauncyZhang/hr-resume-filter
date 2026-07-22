# Agent Workflow

## Start checklist

1. Confirm the exact working directory with `Get-Location`.
2. Read the repository `AGENTS.md` and the relevant `.agents` documents.
3. Identify whether the task belongs to the public product or private enterprise layer.
4. Read the nearest repository README and relevant code before proposing or editing.
5. Run `git status --short --branch` in the exact repository.
6. In the private repository, also run `git submodule status` and `git worktree list` when branch or path ownership matters.
7. Preserve unrelated user changes. Never clean historical worktrees as a convenience.

## Implementation checklist

- Reuse existing module, API, UI, migration, and deployment patterns.
- Keep public and private ownership boundaries intact.
- Add focused tests proportional to the change.
- Keep recruiter-facing text in Simplified Chinese.
- Do not log or expose candidate data, provider keys, credentials, or raw resume content.
- Do not hand-roll PDF, OCR, calendar, or security behavior when the repository already provides a tested abstraction.
- Do not modify production, push branches, or publish releases unless explicitly authorized.

## Verification ladder

Use the narrowest meaningful check first, then broaden according to risk:

1. Focused unit or contract test.
2. Frontend build, backend type/import check, or migration check.
3. Full affected frontend or backend suite.
4. `python scripts/check_public_tree.py` for public changes.
5. `.\验证代码.ps1` for a public-to-private integration update.
6. `.\部署到生产.ps1 -ValidateOnly` for deployment changes.
7. Production health and browser smoke only after an explicitly authorized deployment.

## Finish checklist

1. Run `git diff --check` in every modified repository.
2. Confirm `git status` and list intentionally modified files.
3. If public code changed, confirm its commit exists on the public remote before updating the private submodule pointer.
4. Confirm no enterprise identifiers or secrets entered the public tree.
5. Report tests actually run, failures, and unverified risks.
6. Update these `.agents` documents when repository structure, commands, deployment behavior, or durable constraints change.

## Local workspace cautions

- A parent workspace may contain many repositories. Run Git commands only from the exact intended repository.
- The private repository contains historical linked worktrees, some with uncommitted changes.
- The private main worktree currently retains local `.claude/` and `docs/` directories that are not part of `main`. Do not delete them without explicit approval and inspection.
- Use the standalone public checkout for normal product development and this repository for normal private deployment work.
