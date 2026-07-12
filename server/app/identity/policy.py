from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class Permission(str, Enum):
    MANAGE_USERS = "manage_users"
    MANAGE_SYSTEM = "manage_system"
    MANAGE_AUDIT = "manage_audit"
    READ_RECRUITING = "read_recruiting"
    COMMENT = "comment"
    RECOMMEND_DECISION = "recommend_decision"
    BULK_EXPORT = "bulk_export"
    SEARCH_JOBS = "search_jobs"


GLOBAL_PERMISSIONS = {
    "system_admin": {Permission.MANAGE_USERS, Permission.MANAGE_SYSTEM, Permission.MANAGE_AUDIT},
    "recruiting_admin": {Permission.READ_RECRUITING, Permission.COMMENT, Permission.RECOMMEND_DECISION, Permission.BULK_EXPORT, Permission.SEARCH_JOBS},
}
JOB_PERMISSIONS = {
    "job_owner": {Permission.READ_RECRUITING, Permission.COMMENT, Permission.RECOMMEND_DECISION, Permission.BULK_EXPORT, Permission.SEARCH_JOBS},
    "job_recruiter": {Permission.READ_RECRUITING, Permission.COMMENT, Permission.BULK_EXPORT, Permission.SEARCH_JOBS},
    "job_manager": {Permission.READ_RECRUITING, Permission.COMMENT, Permission.RECOMMEND_DECISION},
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    organization_id: UUID
    roles: frozenset[str]
    active: bool


@dataclass(frozen=True)
class JobGrant:
    job_id: UUID
    organization_id: UUID
    access_role: str


def require_permission(principal: Principal, permission: Permission) -> bool:
    return principal.active and any(permission in GLOBAL_PERMISSIONS.get(role, set()) for role in principal.roles)


def require_job_access(principal: Principal, job_id: UUID, organization_id: UUID, permission: Permission, grants: list[JobGrant]) -> bool:
    if not principal.active or principal.organization_id != organization_id:
        return False
    if require_permission(principal, permission):
        return True
    return any(
        grant.job_id == job_id
        and grant.organization_id == organization_id
        and permission in JOB_PERMISSIONS.get(grant.access_role, set())
        for grant in grants
    )
