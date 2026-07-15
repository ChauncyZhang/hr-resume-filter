from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from server.app.governance.audit import append_audit
from server.app.governance.deletion_models import DeletionRequest
from server.app.queue.service import normalize_safe_code


def finalize_deletion_dead_letter(session, job, safe_code, now) -> None:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict) or set(payload) != {
        "organization_id",
        "deletion_request_id",
        "request_version",
    }:
        return
    try:
        organization_id = UUID(payload["organization_id"])
        request_id = UUID(payload["deletion_request_id"])
        request_version = payload["request_version"]
        if (
            isinstance(request_version, bool)
            or not isinstance(request_version, int)
            or request_version < 1
            or UUID(str(job.organization_id)) != organization_id
        ):
            return
    except (AttributeError, TypeError, ValueError):
        return

    request = session.scalar(
        select(DeletionRequest)
        .where(
            DeletionRequest.organization_id == organization_id,
            DeletionRequest.id == request_id,
            DeletionRequest.version == request_version,
            DeletionRequest.status == "executing",
        )
        .with_for_update()
    )
    if request is None or request.approved_by is None:
        return
    normalized = normalize_safe_code(safe_code)
    request.status = "failed"
    request.safe_error_code = normalized
    request.version += 1
    append_audit(
        session,
        actor=SimpleNamespace(
            organization_id=request.organization_id,
            user_id=request.approved_by,
        ),
        category="governance",
        event_type="governance.deletion_failed",
        outcome="failure",
        trace_id=getattr(job, "trace_id", None),
        resource_type="deletion_request",
        resource_id=request.id,
        metadata={
            "request_version": request.version,
            "safe_error_code": normalized,
        },
    )


def governance_terminal_callbacks() -> dict[str, object]:
    return {"governance.delete_candidate": finalize_deletion_dead_letter}
