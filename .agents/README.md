# BeyondCandidate Agent Handbook

This directory is the durable local handbook for the BeyondCandidate public product and Aurora enterprise deployment repositories.

## Required reading order

1. Read `repository-map.md` to identify the correct repository and ownership boundary.
2. Read `development.md` before changing product code, tests, dependencies, schemas, or the public/private synchronization model.
3. Read `deployment.md` before changing deployment files or touching a remote server.
4. Follow `agent-workflow.md` at the start and end of every task.
5. Read the nearest repository `README.md`, `CONTRIBUTING.md`, and task-specific runbook before editing.

## Repository-relative paths

- Enterprise deployment root: `..` from this directory.
- Pinned public-code submodule: `../product` from this directory.
- Recommended standalone public checkout: sibling directory `../beyondcandidate` relative to this repository's parent.

## Core rule

The public repository is the canonical source for reusable product code. The private repository stores only Aurora deployment configuration, release tooling, and internal documentation. Do not maintain two independent copies of product source.

These documents contain no passwords, private keys, API keys, access tokens, or real candidate data. Keep them that way.
