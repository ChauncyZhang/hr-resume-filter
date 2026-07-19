from datetime import datetime, timezone

from sqlalchemy import select

from server.app.queue.service import normalize_safe_code
from server.app.recruiting.models import ApplicationReviewTask


def ensure_review_task(
    db,
    *,
    application,
    job,
    ai_status: str,
    safe_error_code: str | None = None,
):
    if (
        job.organization_id != application.organization_id
        or job.id != application.job_id
    ):
        raise ValueError("review_task_context_mismatch")
    if ai_status not in {"succeeded", "failed"}:
        raise ValueError("review_task_ai_status_invalid")
    safe_error_code = (
        normalize_safe_code(safe_error_code) if ai_status == "failed" else None
    )
    existing = db.scalar(
        select(ApplicationReviewTask)
        .where(
            ApplicationReviewTask.organization_id == application.organization_id,
            ApplicationReviewTask.application_id == application.id,
            ApplicationReviewTask.status == "open",
        )
        .with_for_update()
    )
    if existing is not None:
        return existing

    task = ApplicationReviewTask(
        organization_id=application.organization_id,
        application_id=application.id,
        assignee_id=job.hiring_owner_id or job.owner_id,
        status="open",
        ai_status=ai_status,
        safe_error_code=safe_error_code,
    )
    db.add(task)
    return task


def close_review_task(db, *, organization_id, application_id):
    task = db.scalar(
        select(ApplicationReviewTask)
        .where(
            ApplicationReviewTask.organization_id == organization_id,
            ApplicationReviewTask.application_id == application_id,
            ApplicationReviewTask.status == "open",
        )
        .with_for_update()
    )
    if task is None:
        return None
    task.status = "closed"
    task.closed_at = datetime.now(timezone.utc)
    return task
