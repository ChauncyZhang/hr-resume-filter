# Development and Synchronization

## Start in the correct repository

Reusable product changes belong in:

```powershell
Set-Location ..\beyondcandidate
```

Aurora-only deployment or internal documentation changes belong in:

```powershell
Set-Location <path-to-hr-resume-filter>
```

Before editing, run `git status --short --branch` in the exact repository. Preserve unrelated and uncommitted work.

## Public product development

Frontend setup and validation:

```powershell
Set-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd test
npm.cmd run build
```

Run a focused frontend test during implementation when possible, then run the full suite before integration.

Backend validation is most reproducible in the pinned test image:

```powershell
Set-Location ..\beyondcandidate
docker build --target test -t beyondcandidate-server-test -f server/Dockerfile .
docker run --rm beyondcandidate-server-test
```

For focused host tests, install `server/requirements-dev.txt` in an isolated Python environment and run the narrow test file first.

Before publishing public changes:

```powershell
python scripts/check_public_tree.py
git diff --check
```

The public repository must not contain enterprise domains, IPs, accounts, secrets, certificates, real resumes, real feedback, or AGPL/SSPL dependencies that have not been explicitly reviewed.

## Product-specific engineering constraints

- Recruiter-facing generated text and structured screening fields must use Simplified Chinese.
- AI screening is advisory routing, not a final hiring or rejection decision.
- Resume processing uses layered extraction: structured/local parsing first, OCR for scanned or low-quality pages, then LLM enrichment when configured.
- LLM screening uses multidimensional scoring and a final score for broad manager handoff. Do not reintroduce the removed rule-based rejection path without an explicit product decision.
- Every provider request must keep thinking disabled. Verify compatibility when adding a provider because some OpenAI-compatible endpoints reject non-standard fields.
- Preserve organization isolation, role authorization, audit records, idempotency, optimistic concurrency, and candidate privacy.
- A resume profile version bump alone does not rebuild existing profiles. Add an explicit backfill or migration when stale persisted profiles must be regenerated.

## Database changes

- Add forward-only Alembic migrations under `server/migrations/versions/`.
- Do not edit an already deployed migration.
- Verify migration head, application-role grants, and affected API tests.
- Application rollback must remain compatible with the forward-migrated schema; do not improvise a production database downgrade.

## Synchronize public changes into the private repository

First commit and push the public change. Then:

```powershell
Set-Location <path-to-hr-resume-filter>
.\更新公共代码.ps1
.\验证代码.ps1
git add product
git commit -m "Update BeyondCandidate product"
git push origin main
```

The private commit records only the new submodule pointer and any intentional Aurora-only changes. Confirm `git submodule status` points to the public commit that was pushed successfully.

## Community local run

From the public repository:

```powershell
.\scripts\setup.ps1
```

This generates local-only credentials, starts the Compose stack, migrates the database, provisions storage, and prints the initial local administrator password once. The default URL is `http://localhost:8080`.
