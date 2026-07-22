# Repository Map

## 1. Public product repository

Recommended local path: sibling checkout `../beyondcandidate` from the internal repository.

Remote: `git@github.com:ChauncyZhang/beyondcandidate.git`

Purpose: reusable, MIT-licensed BeyondCandidate product source. This is the canonical location for frontend, backend, migrations, generic deployment templates, tests, and community setup.

Key directories:

| Path | Responsibility |
| --- | --- |
| `frontend/` | React and Vite browser application, UI controllers, tests, PDF preview |
| `server/` | FastAPI application, workers, domain modules, migrations, backend tests |
| `deploy/` | Generic Docker Compose, Nginx, storage, backup, and observability assets |
| `scripts/` | Community setup and public-tree license or secret checks |
| `README.md` | Community setup, development, production baseline, AI decision notice |
| `THIRD_PARTY_NOTICES.md` | Direct dependency license inventory |

Main runtime components:

- React frontend behind Nginx.
- FastAPI API and Python worker.
- PostgreSQL for durable business data.
- MinIO-compatible object storage for resumes and exports.
- ClamAV for uploaded-file scanning.
- OpenAI-compatible LLM and OCR provider configuration.
- Feishu account binding, calendar availability, and interview synchronization.

## 2. Enterprise deployment repository

Path: the repository containing this `.agents` directory.

Remote: `git@github.com:ChauncyZhang/hr-resume-filter.git`

Purpose: Aurora-only deployment and operations layer. `main` is the canonical internal branch.

Key paths:

| Path | Responsibility |
| --- | --- |
| `product/` | Git submodule pinned to a reviewed public BeyondCandidate commit |
| `deploy/` | Aurora target, shared Nginx protection, release, rollback, and bootstrap scripts |
| `internal-docs/` | HR and hiring-manager operation documents |
| `更新公共代码.ps1` | Fast-forward the public submodule to public `origin/main` |
| `验证代码.ps1` | Public boundary scan, frontend tests/build, private deployment tests |
| `部署到生产.ps1` | Validated one-command production deployment entrypoint |

The repository still contains historical linked worktrees under `.worktrees/` and `.claude/worktrees/`. Some retain uncommitted work. Do not delete, clean, reset, or bulk-edit those directories unless the user explicitly requests it and every affected worktree has been audited.

## 3. Ownership boundary

Change the public repository for:

- Product UI and UX.
- FastAPI APIs, workers, database models, and migrations.
- Resume parsing, OCR, LLM screening, interviews, talent pools, and reports.
- Generic tests, Dockerfiles, Compose definitions, and open-source documentation.

Change the private repository for:

- Aurora domains, server addresses, organization identity, and administrator bootstrap identity.
- TLS file locations and shared website routing.
- Private release, rollback, production smoke, and server bootstrap behavior.
- Internal HR documentation.

Never place Aurora-specific values or real business data in the public repository. Never patch the same product feature separately in both repositories.

## 4. Source flow

```text
beyondcandidate/main
        |
        | reviewed public commit
        v
hr-resume-filter/product (Git submodule pointer)
        |
        | private release tooling and Aurora configuration
        v
/opt/beyondcandidate/releases/<release-id>
        |
        v
/opt/beyondcandidate/current
```
