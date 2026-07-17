LLM_PENDING = {"queued", "running"}
LLM_TERMINAL = {"not_requested", "skipped", "succeeded", "failed"}


def summarize_progress(items, total_count):
    rule_failed = sum(item.status in {"failed", "cancelled"} for item in items)
    rule_succeeded = sum(item.status == "scored" and item.llm_status in LLM_TERMINAL for item in items)
    processed = rule_succeeded + rule_failed
    degraded = any(item.status == "scored" and item.llm_status == "failed" for item in items)
    if processed == total_count:
        status = "partial" if degraded or (rule_succeeded and rule_failed) else "failed" if not rule_succeeded and rule_failed else "completed"
    elif any(item.status == "scored" and item.llm_status in LLM_PENDING for item in items):
        status = "llm_scoring"
    elif any(item.status in {"parsed", "scoring", "scored"} for item in items):
        status = "rule_scoring"
    else:
        status = "parsing"
    return processed, rule_succeeded, rule_failed, status


def aggregate_run(db, run):
    from datetime import datetime,timezone
    from sqlalchemy import select
    from server.app.recruiting.models import Application
    from server.app.recruiting.service import transition_application_record
    from server.app.screening.models import ScreeningItem

    items = list(db.scalars(select(ScreeningItem).where(ScreeningItem.organization_id == run.organization_id, ScreeningItem.run_id == run.id)))
    processed, succeeded, failed, status = summarize_progress(items, run.total_count)
    previous=(run.processed_count,run.succeeded_count,run.failed_count,run.status)
    run.processed_count = processed
    run.succeeded_count = succeeded
    run.failed_count = failed
    run.status = status
    if status in {"completed","partial","failed","cancelled"}: run.finished_at=run.finished_at or datetime.now(timezone.utc)
    else: run.finished_at=None
    if previous!=(processed,succeeded,failed,status): run.version+=1

    completed_application_ids = [
        item.application_id
        for item in items
        if item.status == "scored"
        and item.llm_status in LLM_TERMINAL
        and item.application_id is not None
    ]
    if completed_application_ids:
        applications = list(db.scalars(select(Application).where(
            Application.organization_id == run.organization_id,
            Application.id.in_(completed_application_ids),
            Application.stage == "new",
        )))
        for application in applications:
            transition_application_record(
                db,
                run.organization_id,
                application.id,
                "review",
                expected_version=application.version,
                actor_user_id=run.created_by,
                trace_id=f"screening:auto-review:{run.id}",
            )
