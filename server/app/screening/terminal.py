import uuid
from sqlalchemy import select
from server.app.queue.service import normalize_safe_code
from server.app.screening.models import ScreeningItem,ScreeningRun

def finalize_screening_dead_letter(session,job,safe_code,now):
    try: item_id=uuid.UUID(str(job.payload["screening_item_id"]))
    except (KeyError,TypeError,ValueError): return
    item=session.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==job.organization_id,ScreeningItem.id==item_id).with_for_update())
    if item is None or item.status in {"scored","cancelled"}: return
    item.status="failed"; item.safe_error_code=normalize_safe_code(safe_code); item.finished_at=item.finished_at or now
    run=session.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==job.organization_id,ScreeningRun.id==item.run_id).with_for_update())
    statuses=list(session.scalars(select(ScreeningItem.status).where(ScreeningItem.organization_id==job.organization_id,ScreeningItem.run_id==run.id)))
    succeeded=sum(status=="scored" for status in statuses); failed=sum(status in {"failed","cancelled"} for status in statuses); run.succeeded_count=succeeded; run.failed_count=failed; run.processed_count=succeeded+failed
    if run.processed_count==run.total_count: run.status="completed" if failed==0 else "failed" if succeeded==0 else "partial"
    elif any(status in {"parsed","scoring","scored"} for status in statuses): run.status="rule_scoring"
    else: run.status="parsing"

def screening_terminal_callbacks(): return {"screening.parse_item":finalize_screening_dead_letter,"screening.score_item":finalize_screening_dead_letter}
