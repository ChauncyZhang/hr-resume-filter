from uuid import uuid4

import pytest

from server.app.identity.policy import JobGrant, Permission, Principal, require_job_access, require_permission


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        ("system_admin", Permission.MANAGE_USERS, True),
        ("system_admin", Permission.READ_RECRUITING, False),
        ("recruiting_admin", Permission.READ_RECRUITING, True),
        ("recruiter", Permission.READ_RECRUITING, False),
        ("hiring_manager", Permission.BULK_EXPORT, False),
        ("interviewer", Permission.SEARCH_JOBS, False),
        ("unknown", Permission.MANAGE_USERS, False),
    ],
)
def test_global_role_matrix_fails_closed(role, permission, allowed) -> None:
    principal = Principal(uuid4(), uuid4(), frozenset({role}), True)
    assert require_permission(principal, permission) is allowed


def test_job_grants_are_organization_scoped_and_fail_closed() -> None:
    organization_id = uuid4()
    job_id = uuid4()
    principal = Principal(uuid4(), organization_id, frozenset({"recruiter"}), True)
    grants = [JobGrant(job_id, organization_id, "job_recruiter")]
    assert require_job_access(principal, job_id, organization_id, Permission.READ_RECRUITING, grants)
    assert not require_job_access(principal, job_id, uuid4(), Permission.READ_RECRUITING, grants)
    assert not require_job_access(principal, uuid4(), organization_id, Permission.READ_RECRUITING, grants)
    assert not require_job_access(principal, job_id, organization_id, Permission.MANAGE_USERS, grants)

