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
- `server/app/governance/api.py`
- `server/tests/test_governance_api.py`
- `server/tests/test_governance_postgres.py`

Modified:

- `server/app/main.py`
- `server/app/recruiting/service.py`

No migration or model change was required. The committed `0016` schema and existing
`retention_policy.updated` audit metadata allowlist already provide the persistence
and event contract required by this slice, so `server/app/governance/audit.py` did not
need another allowlist change.

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
- HMAC keys are domain-separated from the configured cursor-secret source.
- Problem responses use stable safe codes and do not include SQL, stack traces,
  credentials, object keys, contacts, resume text, feedback text, or raw audit metadata.
- No schema migration was added. The API consumes Alembic head
  `0016_governance_audit_retention` as required.

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
1 failed, 550 passed, 4 skipped in 818.74s
```

The single failure is existing and outside this task's ownership:
`server/tests/test_postgres_security.py::test_audit_logs_reject_update_and_delete`
performs a raw INSERT into the committed `0016` partitioned `audit_logs` table without
the required non-null `category`, so PostgreSQL raises `NotNullViolation` before that
test reaches its append-only UPDATE/DELETE assertions. This slice did not change the
migration, table constraint, or failing test. The focused governance migration rerun
started afterward was interrupted before producing a result; the full run had already
executed the migration suite and reported only the direct-insert failure above.

## Remaining concern

The full backend gate is not completely green because the pre-existing PostgreSQL
security test's raw INSERT has not been updated for the committed `0016` audit contract.
Fixing that test is outside the brief-owned files and was intentionally not folded into
this commit.
