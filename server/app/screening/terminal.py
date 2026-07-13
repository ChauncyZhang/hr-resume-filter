import uuid
from sqlalchemy import select
from server.app.queue.service import normalize_safe_code
from server.app.screening.models import ScreeningItem,ScreeningRun
from server.app.screening.progress import aggregate_run

def finalize_screening_dead_letter(session,job,safe_code,now):
    try: item_id=uuid.UUID(str(job.payload["screening_item_id"]))
    except (KeyError,TypeError,ValueError): return
    item=session.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==job.organization_id,ScreeningItem.id==item_id).with_for_update())
    if item is None or item.status in {"scored","cancelled"}: return
    item.status="failed"; item.safe_error_code=normalize_safe_code(safe_code); item.finished_at=item.finished_at or now
    run=session.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==job.organization_id,ScreeningRun.id==item.run_id).with_for_update())
    aggregate_run(session,run)

def finalize_llm_dead_letter(session,job,safe_code,now):
    try: item_id=uuid.UUID(str(job.payload["screening_item_id"]))
    except (KeyError,TypeError,ValueError): return
    item=session.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==job.organization_id,ScreeningItem.id==item_id).with_for_update())
    if item is None or item.status!="scored" or item.llm_status in {"succeeded","failed","skipped"}: return
    item.llm_status="failed"; item.llm_safe_error_code=normalize_safe_code(f"llm_{safe_code}"); item.llm_finished_at=item.llm_finished_at or now; item.finished_at=item.finished_at or now
    run=session.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==job.organization_id,ScreeningRun.id==item.run_id).with_for_update())
    if run is not None: aggregate_run(session,run)

def screening_terminal_callbacks(): return {"screening.parse_item":finalize_screening_dead_letter,"screening.score_item":finalize_screening_dead_letter,"screening.llm_score_item":finalize_llm_dead_letter}
