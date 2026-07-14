from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select

from server.app.governance.authorization import (
    audit_authorization_class,
    audit_row_predicate,
    can_edit_retention,
    can_read_retention,
    can_view_recruiting_resource,
)
from server.app.governance.models import RetentionPolicy
from server.app.governance.schemas import (
    AuditCollection,
    RetentionPolicyPatch,
    RetentionPolicyResource,
    RetentionPreviewResource,
    RetentionValues,
)
from server.app.governance.service import (
    GovernanceError,
    GovernanceTokenCodec,
    InvalidGovernanceToken,
    ResourceVersionConflict,
    audit_summary,
    aware,
    policy_projection,
    preview_retention,
    resource_projection,
    update_retention_policy,
)
from server.app.identity.api import problem, session_token
from server.app.identity.models import AuditLog, User
from server.app.identity.service import InvalidSession
from server.app.recruiting.service import IdempotencyConflict, persisted_idempotent


PROBLEM_RESPONSES = {
    status: {"content": {"application/problem+json": {}}}
    for status in (401, 404, 409, 422, 428)
}
router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSES)
ETAG = re.compile(r'^"([1-9][0-9]*)"$')
OUTCOMES = frozenset({"success", "denied", "failure"})


def _response(content, *, status_code=200, etag: int | None = None) -> JSONResponse:
    response = JSONResponse(content, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    if etag is not None:
        response.headers["ETag"] = f'"{etag}"'
    return response


def _safe_problem(request: Request, status: int, code: str) -> JSONResponse:
    response = problem(request, status, code, "The request could not be completed.")
    response.headers["Cache-Control"] = "no-store"
    return response


def _principal(request: Request):
    token = session_token(request)
    if not token:
        return _safe_problem(request, 401, "authentication_required")
    try:
        return request.app.state.identity_service.principal(token)
    except InvalidSession:
        return _safe_problem(request, 401, "authentication_required")


def _denied(request: Request) -> JSONResponse:
    return _safe_problem(request, 404, "resource_not_found")


def _token_codec(request: Request) -> GovernanceTokenCodec:
    return request.app.state.governance_tokens


def _current_time(request: Request) -> datetime:
    return aware(request.app.state.recruiting_clock.current_time())


def _serialized(model, content):
    return model.model_validate(content).model_dump(mode="json")


def _filters_payload(**values):
    return {
        key: value.isoformat() if isinstance(value, datetime) else str(value) if isinstance(value, UUID) else value
        for key, value in values.items()
        if value is not None
    }


@router.get("/audit-logs", response_model=AuditCollection)
def list_audit_logs(
    request: Request,
    from_: datetime | None = Query(None, alias="from"),
    to_: datetime | None = Query(None, alias="to"),
    actor_id: UUID | None = None,
    event_type: str | None = Query(None, min_length=3, max_length=100),
    resource_type: str | None = Query(None, min_length=1, max_length=64),
    resource_id: UUID | None = None,
    outcome: str | None = None,
    cursor: str | None = Query(None, min_length=40, max_length=4096),
    limit: int = Query(50, ge=1, le=100),
):
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    authorization_class = audit_authorization_class(principal)
    if not authorization_class:
        return _denied(request)
    now = _current_time(request)
    start = aware(from_) if from_ is not None else now - timedelta(days=30)
    end = aware(to_) if to_ is not None else now
    if (from_ is not None and from_.tzinfo is None) or (to_ is not None and to_.tzinfo is None):
        return _safe_problem(request, 422, "validation_failed")
    if start > end or end - start > timedelta(days=90):
        return _safe_problem(request, 422, "validation_failed")
    if outcome is not None and outcome not in OUTCOMES:
        return _safe_problem(request, 422, "validation_failed")
    if (resource_id is None) != (resource_type is None):
        return _safe_problem(request, 422, "validation_failed")
    filters = _filters_payload(
        from_=start,
        to=end,
        actor_id=actor_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
    )
    with request.app.state.identity_store.sync_session() as db:
        if resource_id is not None:
            if resource_type == "retention_policy":
                visible = can_read_retention(principal) and db.scalar(
                    select(RetentionPolicy.id).where(
                        RetentionPolicy.organization_id == principal.organization_id,
                        RetentionPolicy.id == resource_id,
                    )
                ) is not None
            else:
                visible = can_view_recruiting_resource(db, principal, resource_type, resource_id)
            if not visible:
                return _denied(request)
        authorization = audit_row_predicate(principal, AuditLog)
        conditions = [
            AuditLog.organization_id == principal.organization_id,
            authorization,
            AuditLog.created_at >= start,
            AuditLog.created_at <= end,
        ]
        if actor_id is not None:
            conditions.append(AuditLog.actor_user_id == actor_id)
        if event_type is not None:
            conditions.append(AuditLog.event_type == event_type)
        if resource_type is not None:
            conditions.append(AuditLog.resource_type == resource_type)
            conditions.append(AuditLog.resource_id == resource_id)
        if outcome is not None:
            conditions.append(AuditLog.outcome == outcome)
        if cursor is not None:
            try:
                decoded = _token_codec(request).decode(cursor)
                expected = {
                    "kind": "audit_cursor",
                    "organization_id": str(principal.organization_id),
                    "authorization_class": authorization_class,
                    "filters": filters,
                }
                if any(decoded.get(key) != value for key, value in expected.items()):
                    raise InvalidGovernanceToken
                cursor_time = datetime.fromisoformat(decoded["created_at"])
                cursor_id = UUID(decoded["id"])
            except (InvalidGovernanceToken, KeyError, TypeError, ValueError):
                return _safe_problem(request, 422, "validation_failed")
            conditions.append(
                or_(
                    AuditLog.created_at < cursor_time,
                    and_(AuditLog.created_at == cursor_time, AuditLog.id < cursor_id),
                )
            )
        rows = db.execute(
            select(AuditLog, User.display_name)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit + 1)
        ).all()
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1][0]
            next_cursor = _token_codec(request).encode(
                {
                    "kind": "audit_cursor",
                    "organization_id": str(principal.organization_id),
                    "authorization_class": authorization_class,
                    "filters": filters,
                    "created_at": aware(last.created_at).isoformat(),
                    "id": str(last.id),
                }
            )
            rows = rows[:limit]
        data = [
            {
                "id": row.id,
                "created_at": aware(row.created_at),
                "actor": {
                    "id": row.actor_user_id,
                    "display_name": display_name or "Deleted user",
                },
                "category": row.category,
                "event_type": row.event_type,
                "resource": resource_projection(
                    db, principal, row.resource_type, row.resource_id
                ),
                "outcome": row.outcome,
                "network_ref": row.ip_hash[:12] if row.ip_hash else None,
                "trace_id": row.trace_id,
                "summary": audit_summary(row.event_type, row.metadata_json),
            }
            for row, display_name in rows
        ]
    return _response(
        _serialized(AuditCollection, {"data": data, "meta": {"next_cursor": next_cursor, "limit": limit}})
    )


@router.get("/settings/retention-policy", response_model=RetentionPolicyResource)
def get_retention_policy(request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    if not can_read_retention(principal):
        return _denied(request)
    with request.app.state.identity_store.sync_session() as db:
        policy = db.scalar(
            select(RetentionPolicy).where(
                RetentionPolicy.organization_id == principal.organization_id
            )
        )
        if policy is None:
            return _denied(request)
        content = _serialized(RetentionPolicyResource, {"data": policy_projection(db, policy)})
    return _response(content, etag=policy.version)


@router.post(
    "/settings/retention-policy/previews", response_model=RetentionPreviewResource
)
def preview_retention_policy(payload: RetentionValues, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    if not can_edit_retention(principal):
        return _denied(request)
    with request.app.state.identity_store.sync_session() as db:
        preview = preview_retention(
            db,
            principal,
            payload.model_dump(),
            _token_codec(request),
            _current_time(request),
        )
        content = _serialized(RetentionPreviewResource, {"data": preview})
    return _response(content)


@router.patch("/settings/retention-policy", response_model=RetentionPolicyResource)
def patch_retention_policy(
    payload: RetentionPolicyPatch,
    request: Request,
    if_match: str | None = Header(None, alias="If-Match"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    principal = _principal(request)
    if isinstance(principal, JSONResponse):
        return principal
    if not can_edit_retention(principal):
        return _denied(request)
    if if_match is None:
        return _safe_problem(request, 428, "precondition_required")
    match = ETAG.fullmatch(if_match)
    if match is None:
        return _safe_problem(request, 422, "validation_failed")
    if not idempotency_key or len(idempotency_key) > 255:
        return _safe_problem(request, 428, "idempotency_key_required")
    expected_version = int(match.group(1))
    values = payload.model_dump(exclude={"impact_token"})
    body = {**payload.model_dump(), "if_match": if_match}
    with request.app.state.identity_store.sync_session() as db:
        try:
            status, response_body = persisted_idempotent(
                db,
                principal.organization_id,
                principal.user_id,
                "retention_policy.update",
                idempotency_key,
                body,
                lambda: (
                    200,
                    _serialized(
                        RetentionPolicyResource,
                        {
                            "data": update_retention_policy(
                                db,
                                principal,
                                values,
                                payload.impact_token,
                                expected_version,
                                _token_codec(request),
                                _current_time(request),
                                request.state.trace_id,
                            )
                        },
                    ),
                ),
            )
            db.commit()
        except IdempotencyConflict:
            db.rollback()
            return _safe_problem(request, 409, "idempotency_conflict")
        except ResourceVersionConflict:
            db.rollback()
            return _safe_problem(request, 409, "resource_version_conflict")
        except GovernanceError as error:
            db.rollback()
            return _safe_problem(request, 409, error.code)
    return _response(response_body, status_code=status, etag=response_body["data"]["version"])
