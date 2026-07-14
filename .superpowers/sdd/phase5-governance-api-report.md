# Phase 5 Governance Task A - Backend API Report

## Status

Implemented the coherent Task A backend slice from base commit `fa55034`.
Frontend work and Task B deletion/legal-hold behavior were not implemented.
The pre-existing dirty files `.superpowers/sdd/task-1-report.md`,
`.superpowers/sdd/task-2-report.md`, and `app/sample/candidates.csv` were not edited,
staged, or reverted by this task.

## Files owned

Created:

- `server/app/governance/schemas.py`
- `server/app/governance/authorization.py`
- `server/app/governance/service.py`
- `server/app/governance/retention.py`
- `server/app/governance/api.py`
- `server/migrations/versions/0016a_audit_category_repair.py`
- `server/tests/test_governance_api.py`
- `server/tests/test_governance_postgres.py`

Modified:

- `server/app/governance/audit.py`
- `server/app/governance/orm.py`
- `server/app/main.py`
- `server/app/recruiting/api.py`
- `server/app/recruiting/service.py`
- `server/app/screening/pipeline.py`
- `server/app/talent/api.py`
- `server/app/interviews/api.py`
- `server/tests/test_governance_migration.py`
- `server/tests/test_llm_api.py`
- `server/tests/test_postgres_security.py` (follow-up audit insert contract)

No model schema was added. The narrow `0016a_audit_category_repair` migration repairs
post-0016 category data before the reserved Task B revision `0017`; governance audit
validation and authoritative category mapping are implemented in
`server/app/governance/audit.py`.

## API and data behavior

- Mounted `GET /api/v1/audit-logs` with a 30-day default range, 90-day maximum,
  validated filters, `created_at DESC, id DESC` ordering, limit 1..100, and an opaque
  HMAC cursor bound to tenant, authorization class, filters, timestamp, and UUID.
- Applied role-union authorization: system administrators receive system/governance
  rows; recruiting administrators receive recruiting/governance rows; recruiters
  receive only their own recruiting rows. Hiring managers and interviewers fail closed.
- Applied tenant predicates before pagination and reused the same authorization
  predicate for row selection and cursor continuation.
- Added current-scope resource projection for jobs, candidates, applications, resumes,
  screening resources, interviews, talent pools/memberships, report exports, and LLM
  configuration. Unauthorized or stale resource scope is redacted; direct resource-ID
  filters fail with `404 resource_not_found`.
- Audit responses expose only allowlisted summaries and safe scalar projections.
  `metadata_json` is never serialized. Network references are limited to the first 12
  lowercase hexadecimal characters of `ip_hash`.
- Mounted retention-policy GET, preview POST, and PATCH contracts. Request models
  forbid extra fields and constrain all day values to 30..3650.
- Preview tokens expire after 10 minutes and bind organization, current policy version,
  proposed values, and a SHA-256 digest of sorted affected candidate UUIDs; candidate
  UUIDs are not present in the token.
- PATCH requires CSRF (existing middleware), `Idempotency-Key`, and quoted `If-Match`.
  It locks the policy row, verifies version/preview state, performs one policy version
  increment, recalculates candidate due dates with one set-based UPDATE, appends
  `retention_policy.updated`, and commits atomically.
- Candidate due dates follow the required active-application null rule and otherwise
  use the latest candidate/application/event/interview/submitted-feedback fact plus
  terminal days, combined with the maximum active talent membership date. Explicit
  membership dates are read but never mutated.
- Every governance response, including validation, authorization, and CSRF failures,
  receives `Cache-Control: no-store`.
- Persisted idempotency now treats an expired row as replaceable under the existing
  PostgreSQL advisory/row lock boundary. Unexpired replay/conflict behavior for existing
  callers is unchanged; replacement rows retain the model's 24-hour lifetime.

## Security and migration notes

- Authorization is server-side, tenant-scoped, and union-based for dual-role principals.
- Direct identifiers do not reveal cross-tenant or unauthorized resource existence.
- Audit cursors and retention previews use separate purpose-derived HMAC keys from the
  configured root secret; neither purpose can verify tokens from the other.
- Problem responses use stable safe codes and do not include SQL, stack traces,
  credentials, object keys, contacts, resume text, feedback text, or raw audit metadata.
- Alembic head includes the pre-Task-B `0016a_audit_category_repair`; revision `0017`
  remains unconsumed for deletion/legal-hold work.

## TDD evidence

RED was observed before production implementation using Python 3.12 in the project test
image:

```text
python -m pytest server/tests/test_governance_api.py -q
7 failed
```

All seven failures were the expected missing-route/OpenAPI failures (`404` or absent
paths). The host default Python 3.14 lacked SQLAlchemy, so all authoritative test evidence
uses the repository's Python 3.12 Docker target.

Focused GREEN after implementation and edge-case expansion:

```text
python -m pytest server/tests/test_governance_api.py -q
8 passed in 16.21s
```

Coverage includes OpenAPI shape, every retention role class, fail-closed denials,
dual-role audit union, tenant isolation, resource redaction, safe summaries/network refs,
equal-timestamp cursor pagination, cursor tamper/filter binding, range validation,
strict payload validation, quoted preconditions, preview requirement/tamper/expiry/stale
impact, idempotency replay/conflict/expiry, active/terminal due dates, talent maximum, and
explicit membership-date preservation.

PostgreSQL concurrency GREEN against an isolated disposable PostgreSQL 16.9 database:

```text
python -m pytest server/tests/test_governance_postgres.py -q
1 passed in 10.04s
```

The two-session barrier produced one successful version-2 PATCH, one
`resource_version_conflict`, and exactly one update audit.

Compilation GREEN:

```text
python -m compileall -q server
exit 0
```

Affected regressions GREEN:

```text
python -m pytest server/tests/test_recruiting.py server/tests/test_recruiting_api.py -q
69 passed in 61.18s

python -m pytest server/tests/test_screening_api.py server/tests/test_talent_api.py server/tests/test_reports_api.py -q
36 passed in 48.28s
```

Full PostgreSQL-enabled backend result:

```text
python -m pytest server/tests -q
551 passed, 4 skipped
```

The audit insert contract was corrected in follow-up commit `721a88b`; its targeted
PostgreSQL audit check passed (`1 passed`). The final-range full gate then passed with
the result above. This corrects the superseded intermediate failed result that was
previously recorded here.

## Review fix wave (2026-07-14)

All seven Important findings in `phase5-governance-api-review.md` were addressed without
implementing deletion/legal-hold Task B or consuming revision `0017`:

- Added one authoritative event-to-category mapping. The ORM `before_insert` boundary
  applies it to every active direct `AuditLog` producer, while `append_audit` rejects an
  explicitly inconsistent category. Real recruiting-producer and dual-role tests prove
  the intended recruiting/system/governance role union.
- Added `0016a_audit_category_repair`, ordered directly after `0016`. It temporarily
  drops the append-only trigger, repairs only mismatched category values with the same
  mapping, and restores the trigger in the same migration transaction. Its downgrade
  intentionally retains the authoritative repaired data; Task B can still use `0017`.
- Made any active application override talent membership and produce a null due date.
- Changed submitted feedback retention facts to use `InterviewFeedback.updated_at`, so
  amendments extend retention from the submitted fact's latest version.
- Recalculation and active-application clearing use table-level updates that explicitly
  preserve `Candidate.updated_at`.
- Added a shared candidate-row lock boundary. Retention PATCH locks all tenant candidates
  in deterministic ID order before reading facts; manual, screening, and talent-pool
  application creation lock the same candidate before creating an active application and
  clear its due date in the same transaction. The PostgreSQL barrier test proves the
  concurrent operations serialize to a committed active application with null due date;
  it does not retry or accept a stale result.
- Added governance-path-family no-store middleware. Redirects, validation/auth failures,
  successful responses, and safely converted unexpected errors all receive
  `Cache-Control: no-store`.
- Also completed the review's non-blocking hardening: actor display-name joins are
  tenant-qualified and malformed/non-lowercase/non-SHA-256 `ip_hash` values expose no
  network prefix. The second review later strengthened cursor/preview separation to
  distinct purpose-derived HMAC keys.

Atomicity coverage injects an audit failure after policy and due-date changes and proves
rollback of policy version, due date, idempotency record, and update audit. Existing
governance tests continue to cover direct-ID non-enumeration and cursor tenant/filter/role
rebinding. PostgreSQL coverage also proves concurrent replacement of one expired
idempotency key executes the replacement action exactly once.

### Review-wave TDD evidence

Expected RED before production fixes:

```text
python -m pytest server/tests/test_governance_api.py -q
5 failed, 7 passed in 17.62s

POSTGRES_SMOKE_URL=... python -m pytest server/tests/test_governance_postgres.py -q
1 failed, 2 passed in 19.45s

POSTGRES_SMOKE_URL=... python -m pytest \
  server/tests/test_governance_migration.py::test_post_0016_audit_category_repair_preserves_append_only_trigger -q
1 failed in 12.22s
```

The RED failures demonstrated the exact reviewed defects: system-classified recruiting
producer, changed candidate timestamp, active-plus-talent non-null due, redirect/internal
responses without no-store, stale concurrent retention result, and unrepaired post-0016
category data.

Final focused GREEN in the Python 3.12 test image:

```text
python -m pytest server/tests/test_governance_api.py server/tests/test_governance_models.py -q
14 passed in 24.57s
```

Final PostgreSQL 16.9 governance/concurrency/migration GREEN:

```text
POSTGRES_SMOKE_URL=... python -m pytest \
  server/tests/test_governance_postgres.py server/tests/test_governance_migration.py -q
10 passed in 110.58s
```

The first affected run exposed an unintended service validation change in two legacy
fixtures (`146 passed, 2 failed`). Removing only that new validation preserved the shared
lock for real candidates; the exact regressions then passed (`2 passed in 1.26s`). Final
affected GREEN:

```text
python -m pytest \
  server/tests/test_recruiting.py server/tests/test_recruiting_api.py \
  server/tests/test_screening_api.py server/tests/test_screening_pipeline.py \
  server/tests/test_talent_api.py server/tests/test_interview_api.py \
  server/tests/test_reports_api.py server/tests/test_llm_api.py -q
148 passed in 247.38s
```

Compilation and patch hygiene:

```text
python -m compileall -q server
exit 0

git diff --check
exit 0
```

Final PostgreSQL-enabled backend gate:

```text
POSTGRES_SMOKE_URL=... python -m pytest server/tests -q
558 passed, 4 skipped in 885.80s
```

### Remaining concerns

- This review-wave snapshot had no known failing test; later independent review findings
  and their resolutions are recorded below.
- The category repair intentionally performs controlled updates while its append-only
  trigger is absent inside one transactional migration. Deployments should apply it as a
  normal exclusive schema migration before any future `0017` Task B migration.

## Second independent review fix wave (2026-07-14)

All three additional Important findings and the requested Minor were closed without
frontend or Task B changes:

- Product authorization decision: `llm.config_updated` and
  `llm.connection_tested` describe deployment-level provider configuration managed by
  system administrators, so every `llm.*` audit event is explicitly mapped to `system`.
  `CATEGORY_PREFIXES`, the ORM persistence boundary, and `0016a` use that same decision;
  the migration repairs incorrectly recruiting-classified LLM history. A real LLM API
  producer matrix proves visibility for system administrators and dual-role users,
  invisibility for recruiting administrators/recruiters, and fail-closed behavior for
  hiring managers/interviewers.
- Added `server.app.governance.retention`, a narrow model-level dependency with no service
  imports. It owns deterministic candidate locking, retention fact queries, timestamp-
  preserving due updates, and single-candidate recalculation. Governance PATCH and all
  fact writers share this boundary without recruiting/governance service cycles.
- Immediate in-transaction recalculation now follows candidate profile/event writes,
  application create/update/transition paths (including screening and reactivation),
  interview create/update/transition paths, submitted feedback and amendments, and talent
  membership create/update/delete. Draft feedback is intentionally excluded because the
  retention query includes only submitted/amended status.
- Three PostgreSQL two-session barriers pause retention PATCH after its old fact snapshot,
  then start real talent-membership, feedback-amendment, or candidate-event HTTP writes.
  Each writer must block on the shared candidate row; after PATCH commits it acquires the
  lock, writes, recalculates, and leaves stored due equal to the final committed fact set.
- Audit cursor and retention preview codecs now derive distinct HMAC keys from the root
  secret using explicit purpose labels. Tests prove key inequality and cross-purpose
  verification rejection.

### Second-review TDD evidence

Expected RED before implementation:

```text
python -m pytest \
  server/tests/test_governance_api.py::test_llm_audit_events_are_explicitly_system_and_governance_keys_are_domain_separated -q
1 failed

POSTGRES_SMOKE_URL=... python -m pytest \
  server/tests/test_governance_postgres.py::test_retention_patch_serializes_with_every_retention_fact_writer -q
3 failed in 13.81s
```

The first test failed because no explicit category-prefix table/key derivation API existed.
The PostgreSQL tests demonstrated stale final due dates for talent and candidate events;
the corrected feedback payload separately proved its writer completed without waiting for
the candidate lock (`writer_was_serialized == False`).

Final focused GREEN:

```text
python -m pytest server/tests/test_governance_api.py \
  server/tests/test_governance_models.py server/tests/test_llm_api.py -q
17 passed in 19.59s
```

Final PostgreSQL migration/concurrency GREEN:

```text
POSTGRES_SMOKE_URL=... python -m pytest \
  server/tests/test_governance_postgres.py server/tests/test_governance_migration.py -q
13 passed in 84.81s
```

Affected GREEN:

```text
python -m pytest server/tests/test_recruiting.py server/tests/test_recruiting_api.py \
  server/tests/test_screening_api.py server/tests/test_screening_pipeline.py \
  server/tests/test_screening_actions.py server/tests/test_talent_api.py \
  server/tests/test_interview_api.py server/tests/test_llm_api.py -q
138 passed in 169.12s
```

Final PostgreSQL-enabled backend gate:

```text
POSTGRES_SMOKE_URL=... python -m pytest server/tests -q
562 passed, 4 skipped in 850.39s
```

Compilation and patch hygiene:

```text
python -m compileall -q server
exit 0

git diff --check
exit 0
```

### Final concerns

- This second-review snapshot had no known failing test; the third independent review
  findings and their resolutions are recorded below.
- `0016a` retains its controlled transactional trigger drop/repair/recreate behavior and
  must be deployed before any future Task B `0017` migration.

## Third independent review fix wave (2026-07-14)

The two third-review Important findings were addressed without frontend or Task B
changes:

- `recalculate_due_dates` now restricts its physical `UPDATE` to the exact candidate IDs
  present in the computed due-date mapping, in addition to the organization predicate.
  A PostgreSQL two-candidate test recalculates each candidate independently while the
  other row is locked and proves that the unrelated row's `retention_due_at`,
  `updated_at`, `version`, and PostgreSQL `xmin` remain unchanged. Both directions finish
  within explicit lock/statement timeouts, proving that unrelated candidate rows are not
  locked and no deadlock occurs.
- All retention-fact mutation paths were audited and normalized to Candidate first,
  business fact second. Application transition now performs a tenant-scoped candidate-ID
  pre-read, locks Candidate, then tenant-scoped locks and revalidates Application version
  and candidate relationship. Interview create/update/transition, submitted-feedback
  submit/amend, talent membership update/delete/reactivation, and application completion
  advancement follow the same ordering and revalidate the pre-read relationship after
  locking. Talent creation and the existing candidate/application/event writers already
  lock Candidate before inserting facts.
- Screening bulk action no longer pre-locks Application rows before calling the shared
  Candidate-first transition service. Screening run/item locks remain earlier because
  they are not candidate retention facts and no Candidate-first path subsequently locks
  those rows.
- PostgreSQL writer barriers set `lock_timeout` and `statement_timeout`. They prove
  application transition versus application patch completes without deadlock and yields
  the version-correct winner, and prove feedback amendment and talent membership patch
  wait on Candidate before acquiring their business rows. Stored `retention_due_at` is
  checked against the final committed fact set after every barrier.

### Third-review TDD evidence

Expected RED before implementation:

```text
POSTGRES_SMOKE_URL=... python -m pytest server/tests/test_governance_postgres.py \
  -k "single_candidate_recalculation or application_transition_and_patch or fact_writer_waits" -q
4 failed, 6 deselected in 23.84s
```

The failures were specific to the review findings: single-candidate recalculation timed
out while updating a locked unrelated candidate; application patch could not complete
while transition paused before its Candidate lock; and both feedback amendment and talent
patch had already locked their business row while blocked on Candidate.

Final focused GREEN:

```text
python -m pytest server/tests/test_governance_api.py server/tests/test_governance_models.py \
  server/tests/test_llm_api.py server/tests/test_recruiting.py -q
39 passed in 22.87s
```

Final PostgreSQL migration/concurrency GREEN, including the symmetric two-candidate
isolation check and all writer barriers:

```text
POSTGRES_SMOKE_URL=... python -m pytest \
  server/tests/test_governance_postgres.py server/tests/test_governance_migration.py -q
17 passed in 120.55s
```

Submission self-review replaced the feedback/talent test's fixed startup delay with a
real event barrier at the Candidate lock call and added per-writer lock/statement
timeouts. The finalized four new concurrency cases passed together (`4 passed, 6
deselected in 16.97s`) before the complete 17-test result above.

One earlier combined PostgreSQL run reached `16 passed` and then the final migration test
failed while asyncpg opened a connection with `TimeoutError`; PostgreSQL had one of 100
connections active and no test assertion had failed. The exact test passed on a fresh
PostgreSQL 16.9 container (`1 passed in 11.19s`), followed by the clean 17-test result
above.

The first affected run exposed three legacy SQLite aggregate fixtures that intentionally
create Application without Candidate (`150 passed, 3 failed`). Keeping the shared lock
call while removing the newly introduced candidate-existence requirement preserved that
fixture contract; the recruiting module then passed (`22 passed in 1.72s`). Final
affected GREEN:

```text
python -m pytest server/tests/test_recruiting.py server/tests/test_recruiting_api.py \
  server/tests/test_screening_api.py server/tests/test_screening_pipeline.py \
  server/tests/test_screening_actions.py server/tests/test_talent_api.py \
  server/tests/test_interview_api.py server/tests/test_llm_api.py -q
138 passed in 158.97s
```

Final PostgreSQL-enabled backend gate:

```text
POSTGRES_SMOKE_URL=... python -m pytest server/tests -q
566 passed, 4 skipped in 848.21s
```

Compilation and patch hygiene:

```text
python -m compileall -q server
exit 0

git diff --check
exit 0
```

### Third-review files changed

- `server/app/governance/retention.py`
- `server/app/recruiting/service.py`
- `server/app/recruiting/api.py`
- `server/app/screening/actions.py`
- `server/app/interviews/api.py`
- `server/app/talent/api.py`
- `server/tests/test_governance_postgres.py`
- `server/tests/test_postgres_security.py`
- `server/tests/test_recruiting.py`
- `.superpowers/sdd/phase5-governance-api-report.md`

### Third-review concerns

- The specified third-review findings have implementation and test evidence, but this
  report does not claim an independent post-fix review is clean; that conclusion belongs
  to the next independent review.
- No test is currently failing. The one asyncpg connection timeout was reproduced only
  as an infrastructure transient and passed both exact and full-combination reruns on a
  fresh PostgreSQL container.
