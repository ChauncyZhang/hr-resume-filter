# Task B3A Report

## Status

Implemented the active legal-hold status contract within the four B3A-owned
files. No endpoint, deployment, frontend, B2B1, or user-file changes were made.

## Files owned

- `server/app/governance/schemas.py`
- `server/app/governance/api.py`
- `server/tests/test_governance_deletion_api.py`
- `.superpowers/sdd/task-b3a-report.md`

## API and data behavior

- Added optional `legal_hold_id` and `legal_hold_version` fields to
  `GovernanceStatusOut`.
- The existing candidate governance-status endpoint returns the active hold's
  exact ID, version, and reason only to a principal with `recruiting_admin`.
- The fields are sourced from the same active `LegalHold` row used to compute
  `legal_hold_active`; rows with `released_at` set remain excluded.
- Existing response fields, `Cache-Control: no-store`, read audit behavior, and
  safe non-enumerating 404 behavior are unchanged.

## Security and migration notes

- Recruiter responses continue to expose only the existing status fields and
  do not include hold reason, ID, or version.
- Cross-tenant direct candidate IDs remain non-enumerating for every existing
  role in the B2A matrix, and an injected unknown role also fails closed without
  exposing hold existence, reason, or ID.
- Released holds do not expose reason, ID, or version even to a recruiting
  administrator.
- No persistence model or database migration was required; the response uses
  existing `LegalHold.id` and `LegalHold.version` columns.

## Tests and verification

- TDD RED:
  `docker run --rm --mount "type=bind,source=$PWD,target=/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py::test_legal_hold_release_and_governance_status_redact_reason_by_role server/tests/test_governance_deletion_api.py::test_all_b2a_endpoints_are_non_enumerating_for_known_cross_tenant_ids -q`
  -> `1 failed, 1 passed`; the administrator status lacked
  `legal_hold_id` and `legal_hold_version`.
- B3A focused GREEN: the same two tests -> `2 passed in 9.25s`.
- Existing B2A focused API regression:
  `docker run --rm --mount "type=bind,source=$PWD,target=/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_deletion_api.py -q`
  -> `21 passed in 39.67s`.
- Existing governance API regression:
  `docker run --rm --mount "type=bind,source=$PWD,target=/opt/ux09" -w /opt/ux09 ux09-server-test python -m pytest server/tests/test_governance_api.py -q`
  -> `13 passed in 21.29s`.
- Python 3.12 `compileall` over the three owned Python files passed.
- Scoped `git diff --check` over all B3A-owned files passed.

## Remaining risk

The change is response-only and exercised against SQLite through the focused
API suites. No PostgreSQL-specific behavior or migration changed, so a
PostgreSQL integration run was not required by the B3A brief.
