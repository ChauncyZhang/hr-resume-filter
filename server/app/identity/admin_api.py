from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from server.app.identity.api import problem, session_token
from server.app.identity.models import (
    AuditLog,
    Department,
    Job,
    PasswordInvitation,
    User,
    UserRole,
    UserStatus,
)
from server.app.identity.policy import Principal
from server.app.identity.security import PasswordService, hash_token
from server.app.identity.service import InvalidSession


router = APIRouter(prefix="/api/v1/settings")
ADMIN_ROLES = {"system_admin", "recruiting_admin"}
ORGANIZATION_READ_ROLES = ADMIN_ROLES | {"recruiter"}
INVITABLE_ROLES = {
    "system_admin",
    "recruiting_admin",
    "recruiter",
    "hiring_manager",
    "interviewer",
}
RECRUITING_ADMIN_INVITABLE_ROLES = {
    "recruiter",
    "hiring_manager",
    "interviewer",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DepartmentCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("department name is required")
        return value


class UserInvite(StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    department_id: UUID | None
    role: Literal[
        "system_admin",
        "recruiting_admin",
        "recruiter",
        "hiring_manager",
        "interviewer",
    ]

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("display name is required")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip()
        if value.count("@") != 1 or not all(value.split("@")):
            raise ValueError("invalid email address")
        return value


def _principal(
    request: Request, allowed_roles: set[str] = ADMIN_ROLES
) -> Principal | JSONResponse:
    token = session_token(request)
    if not token:
        return problem(
            request, 401, "authentication_required", "Authentication is required."
        )
    try:
        principal = request.app.state.identity_service.principal(token)
    except InvalidSession:
        return problem(
            request, 401, "authentication_required", "Authentication is required."
        )
    if not principal.roles.intersection(allowed_roles):
        return problem(
            request, 403, "authorization_forbidden", "The action is not permitted."
        )
    return principal


def _department_data(department: Department, members: int, jobs: int) -> dict:
    return {
        "id": str(department.id),
        "name": department.name,
        "parent_id": str(department.parent_id) if department.parent_id else None,
        "member_count": members,
        "job_count": jobs,
    }


def _user_data(user: User, department_name: str | None) -> dict:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "department_id": str(user.department_id) if user.department_id else None,
        "department_name": department_name,
        "roles": sorted(role.role for role in user.roles),
        "status": user.status.value,
    }


@router.get("/departments")
def list_departments(request: Request):
    principal = _principal(request, ORGANIZATION_READ_ROLES)
    if isinstance(principal, JSONResponse):
        return principal
    member_count = (
        select(func.count(User.id))
        .where(
            User.organization_id == Department.organization_id,
            User.department_id == Department.id,
        )
        .correlate(Department)
        .scalar_subquery()
    )
    job_count = (
        select(func.count(Job.id))
        .where(
            Job.organization_id == Department.organization_id,
            Job.department_id == Department.id,
        )
        .correlate(Department)
        .scalar_subquery()
    )
    with request.app.state.identity_store.sync_session() as db:
        rows = db.execute(
            select(Department, member_count, job_count)
            .where(Department.organization_id == principal.organization_id)
            .order_by(Department.name, Department.id)
        ).all()
        return {
            "data": [
                _department_data(department, members, jobs)
                for department, members, jobs in rows
            ]
        }


@router.post("/departments", status_code=201)
def create_department(payload: DepartmentCreate, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    with request.app.state.identity_store.sync_session() as db:
        if payload.parent_id is not None and db.scalar(
            select(Department.id).where(
                Department.organization_id == principal.organization_id,
                Department.id == payload.parent_id,
            )
        ) is None:
            return problem(
                request, 422, "department_invalid", "The department is invalid."
            )
        duplicate = db.scalar(
            select(Department.id).where(
                Department.organization_id == principal.organization_id,
                Department.parent_id == payload.parent_id,
                Department.name == payload.name,
            )
        )
        if duplicate is not None:
            return problem(
                request,
                409,
                "department_already_exists",
                "The department already exists.",
            )
        department = Department(
            organization_id=principal.organization_id,
            parent_id=payload.parent_id,
            name=payload.name,
        )
        db.add(department)
        try:
            db.flush()
            db.add(
                AuditLog(
                    organization_id=principal.organization_id,
                    actor_user_id=principal.user_id,
                    category="system",
                    event_type="organization.department_created",
                    outcome="success",
                    resource_type="department",
                    resource_id=department.id,
                    trace_id=request.state.trace_id,
                    metadata_json={},
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            return problem(
                request,
                409,
                "department_already_exists",
                "The department already exists.",
            )
        return JSONResponse(
            {"data": _department_data(department, 0, 0)}, status_code=201
        )


@router.get("/users")
def list_users(request: Request):
    principal = _principal(request, ORGANIZATION_READ_ROLES)
    if isinstance(principal, JSONResponse):
        return principal
    with request.app.state.identity_store.sync_session() as db:
        rows = db.execute(
            select(User, Department.name)
            .options(selectinload(User.roles))
            .outerjoin(
                Department,
                (Department.organization_id == User.organization_id)
                & (Department.id == User.department_id),
            )
            .where(User.organization_id == principal.organization_id)
            .order_by(User.display_name, User.id)
        ).all()
        return {"data": [_user_data(user, name) for user, name in rows]}


@router.post("/users", status_code=201)
def invite_user(
    payload: UserInvite,
    request: Request,
    idempotency_key: str | None = Header(None),
):
    del idempotency_key
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    if (
        "system_admin" not in principal.roles
        and payload.role not in RECRUITING_ADMIN_INVITABLE_ROLES
    ):
        return problem(
            request,
            403,
            "role_assignment_forbidden",
            "The role cannot be assigned.",
        )
    if payload.role not in INVITABLE_ROLES:
        return problem(
            request,
            422,
            "validation_failed",
            "The request is invalid.",
        )

    normalized_email = payload.email.casefold()
    now = request.app.state.identity_service.clock.current_time()
    raw_token = request.app.state.identity_service.tokens.new_token()
    with request.app.state.identity_store.sync_session() as db:
        if payload.department_id is not None:
            department = db.scalar(
                select(Department).where(
                    Department.organization_id == principal.organization_id,
                    Department.id == payload.department_id,
                )
            )
            if department is None:
                return problem(
                    request, 422, "department_invalid", "The department is invalid."
                )
        else:
            department = None
        if db.scalar(
            select(User.id).where(
                User.organization_id == principal.organization_id,
                User.normalized_email == normalized_email,
            )
        ) is not None:
            return problem(
                request,
                409,
                "user_email_already_exists",
                "The email already exists.",
            )

        user = User(
            organization_id=principal.organization_id,
            department_id=payload.department_id,
            email=payload.email,
            normalized_email=normalized_email,
            display_name=payload.display_name,
            password_hash=PasswordService().hash(secrets.token_urlsafe(48)),
            status=UserStatus.INVITED,
        )
        user.roles.append(UserRole(role=payload.role))
        db.add(user)
        expires_at = now + timedelta(hours=48)
        try:
            db.flush()
            db.add(
                PasswordInvitation(
                    organization_id=principal.organization_id,
                    user_id=user.id,
                    token_hash=hash_token(raw_token),
                    expires_at=expires_at,
                )
            )
            db.add(
                AuditLog(
                    organization_id=principal.organization_id,
                    actor_user_id=principal.user_id,
                    category="system",
                    event_type="identity.user_invited",
                    outcome="success",
                    resource_type="user",
                    resource_id=user.id,
                    trace_id=request.state.trace_id,
                    metadata_json={},
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            return problem(
                request,
                409,
                "user_email_already_exists",
                "The email already exists.",
            )
        return JSONResponse(
            {
                "data": {
                    "user": _user_data(
                        user, department.name if department is not None else None
                    ),
                    "invitation": {
                        "token": raw_token,
                        "expires_at": expires_at.isoformat(),
                    },
                }
            },
            status_code=201,
        )
