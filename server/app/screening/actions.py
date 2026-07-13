import uuid
from sqlalchemy import select
from server.app.queue.models import BackgroundJob
from server.app.queue.repository import QueueRepository
from server.app.recruiting.models import Application,FileObject,Resume
from server.app.recruiting.service import transition_application_record
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.progress import aggregate_run
from server.app.screening.rules import ENGINE_VERSION

RECOVERABLE_CODES={"scanner_unavailable","storage_unavailable","scanner_error","scoring_failed","parser_timeout","queue_unavailable"}
class ScreeningActionConflict(Exception): pass
class ScreeningItemNotRetryable(ScreeningActionConflict): pass
class ScreeningRetryActive(ScreeningActionConflict): pass
class ScreeningBulkConflict(ScreeningActionConflict): pass

def retry_screening_item(db,organization_id,item_id,trace_id):
    item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update())
    if item is None: raise ScreeningItemNotRetryable
    run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==item.run_id).with_for_update()); stored_file=db.scalar(select(FileObject).where(FileObject.organization_id==organization_id,FileObject.id==item.file_object_id).with_for_update())
    if run is None or stored_file is None: raise ScreeningItemNotRetryable
    if item.status!="failed" or item.safe_error_code not in RECOVERABLE_CODES: raise ScreeningItemNotRetryable
    jobs=list(db.scalars(select(BackgroundJob).where(BackgroundJob.organization_id==organization_id,BackgroundJob.dedupe_key.in_((f"parse:{item.id}",f"score:{item.id}"))).with_for_update()))
    if any(job.status in {"queued","running"} for job in jobs): raise ScreeningRetryActive
    if db.scalar(select(ScreeningResult.id).where(ScreeningResult.organization_id==organization_id,ScreeningResult.item_id==item.id)): raise ScreeningItemNotRetryable
    parsed=bool(item.resume_id and item.application_id)
    if parsed and (db.scalar(select(Resume.id).where(Resume.organization_id==organization_id,Resume.id==item.resume_id)) is None or db.scalar(select(Application.id).where(Application.organization_id==organization_id,Application.id==item.application_id,Application.job_id==run.job_id)) is None): raise ScreeningItemNotRetryable
    if not parsed and stored_file.storage_state not in {"quarantine","clean"}: raise ScreeningItemNotRetryable
    if not parsed and stored_file.scan_status=="rejected": raise ScreeningItemNotRetryable
    run.finished_at=None; run.version+=1
    item.status="parsed" if parsed else "queued"; item.safe_error_code=None; item.finished_at=None
    db.flush(); aggregate_run(db,run)
    queue=QueueRepository(db)
    if parsed:
        job=queue.enqueue(organization_id,"screening.score_item",{"organization_id":str(organization_id),"screening_item_id":str(item.id),"jd_version_id":str(run.jd_version_id),"rule_version_id":str(run.rule_version_id),"rule_engine_version":ENGINE_VERSION},dedupe_key=f"score:{item.id}",trace_id=trace_id,max_attempts=3)
    else:
        job=queue.enqueue(organization_id,"screening.parse_item",{"organization_id":str(organization_id),"screening_item_id":str(item.id),"parser_version":"parser-v1"},dedupe_key=f"parse:{item.id}",trace_id=trace_id,max_attempts=3)
    db.flush(); return item,run,job

def apply_bulk_action(db,organization_id,run_id,payload,actor_user_id,trace_id):
    run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==run_id).with_for_update())
    requested={item.item_id:item.expected_application_version for item in payload.items}; rows=list(db.scalars(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.run_id==run_id,ScreeningItem.id.in_(requested)).order_by(ScreeningItem.id).with_for_update()))
    if run is None or len(rows)!=len(requested): raise ScreeningBulkConflict
    if any(item.status!="scored" or item.application_id is None or not db.scalar(select(ScreeningResult.id).where(ScreeningResult.organization_id==organization_id,ScreeningResult.item_id==item.id)) for item in rows): raise ScreeningBulkConflict
    applications=list(db.scalars(select(Application).where(Application.organization_id==organization_id,Application.id.in_([item.application_id for item in rows])).order_by(Application.id).with_for_update()))
    if len(applications)!=len(rows): raise ScreeningBulkConflict
    by_id={application.id:application for application in applications}; decisions=[]
    for item in rows:
        application=by_id[item.application_id]; expected=requested[item.id]; target="review" if payload.command=="advance_to_review" else "rejected"
        if application.stage==target and application.version==expected+1: decisions.append((application,"already_applied",target)); continue
        if application.version!=expected: raise ScreeningBulkConflict
        if payload.command=="advance_to_review" and application.stage!="new": raise ScreeningBulkConflict
        if payload.command=="reject" and application.stage in {"hired","rejected","withdrawn"}: raise ScreeningBulkConflict
        decisions.append((application,"applied",target))
    output=[]
    for application,result,target in decisions:
        if result=="applied": application=transition_application_record(db,application.id,target,expected_version=application.version,actor_user_id=actor_user_id,trace_id=trace_id,reason_code=payload.reason_code,reason_text=payload.reason_text)
        output.append({"id":str(application.id),"stage":application.stage,"version":application.version,"result":result})
    db.flush(); return {"command":payload.command,"applied_count":sum(item["result"]=="applied" for item in output),"already_applied_count":sum(item["result"]=="already_applied" for item in output),"applications":output}
