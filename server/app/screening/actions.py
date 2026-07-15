import uuid
from sqlalchemy import and_, select
from server.app.identity.models import AuditLog
from server.app.llm.models import LlmProviderConfig,PromptVersion
from server.app.queue.models import BackgroundJob
from server.app.queue.repository import QueueRepository
from server.app.recruiting.models import Application,Candidate,FileObject,Resume
from server.app.recruiting.service import CandidateUnavailable,lock_active_candidate,transition_application_record
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.progress import aggregate_run
from server.app.screening.rules import ENGINE_VERSION

RECOVERABLE_CODES={"scanner_unavailable","storage_unavailable","scanner_error","scoring_failed","parser_timeout","queue_unavailable"}
LLM_RECOVERABLE_CODES={"provider_unavailable","provider_quota_or_rate_limited","provider_response_invalid"}
class ScreeningActionConflict(Exception): pass
class ScreeningItemNotRetryable(ScreeningActionConflict): pass
class ScreeningRetryActive(ScreeningActionConflict): pass
class ScreeningBulkConflict(ScreeningActionConflict): pass

def llm_error_code(code):
    return code[4:] if isinstance(code,str) and code.startswith("llm_") else code

def has_recoverable_llm_failure(item):
    return item.status=="scored" and item.llm_status=="failed" and llm_error_code(item.llm_safe_error_code) in LLM_RECOVERABLE_CODES

def is_llm_retryable(item,run,result,config,prompt):
    if not has_recoverable_llm_failure(item) or run is None or result is None or config is None or prompt is None: return False
    if result.application_id!=item.application_id or result.resume_id!=item.resume_id: return False
    allowed=not config.allowed_job_ids or str(run.job_id) in config.allowed_job_ids
    return bool(config.enabled and config.encrypted_api_key is not None and allowed)

def _active_retry_jobs(db,organization_id,item_id):
    jobs=list(db.scalars(select(BackgroundJob).where(BackgroundJob.organization_id==organization_id,BackgroundJob.status.in_(("queued","running")),((BackgroundJob.dedupe_key.in_((f"parse:{item_id}",f"score:{item_id}"))) | (BackgroundJob.type=="screening.llm_score_item"))).order_by(BackgroundJob.id).with_for_update()))
    return [job for job in jobs if job.dedupe_key in {f"parse:{item_id}",f"score:{item_id}"} or str(job.payload.get("screening_item_id"))==str(item_id)]

def _audit_retry(db,item,actor_user_id,trace_id,retry_stage):
    if actor_user_id is not None:
        db.add(AuditLog(organization_id=item.organization_id,actor_user_id=actor_user_id,event_type="screening.item_retried",outcome="success",trace_id=trace_id,metadata_json={"run_id":str(item.run_id),"item_id":str(item.id),"retry_stage":retry_stage}))

def retry_screening_item(db,organization_id,item_id,trace_id,actor_user_id=None):
    active_jobs=_active_retry_jobs(db,organization_id,item_id)
    item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update())
    if item is None: raise ScreeningItemNotRetryable
    if item.candidate_id is not None:
        try: lock_active_candidate(db,organization_id,item.candidate_id)
        except CandidateUnavailable: raise ScreeningItemNotRetryable from None
    run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==item.run_id).with_for_update()); stored_file=db.scalar(select(FileObject).where(FileObject.organization_id==organization_id,FileObject.id==item.file_object_id).with_for_update())
    if run is None or stored_file is None: raise ScreeningItemNotRetryable
    llm_active=any(job.type=="screening.llm_score_item" for job in active_jobs)
    if item.status=="scored" and (llm_active or item.llm_status in {"queued","running"}): raise ScreeningRetryActive
    if has_recoverable_llm_failure(item):
        result=db.scalar(select(ScreeningResult).where(ScreeningResult.organization_id==organization_id,ScreeningResult.item_id==item.id,ScreeningResult.application_id==item.application_id,ScreeningResult.resume_id==item.resume_id).order_by(ScreeningResult.created_at.desc(),ScreeningResult.id.desc()).limit(1).with_for_update())
        config=db.scalar(select(LlmProviderConfig).where(LlmProviderConfig.organization_id==organization_id).with_for_update())
        prompt=db.scalar(select(PromptVersion).where(PromptVersion.organization_id==organization_id,PromptVersion.name=="screening-evaluation").order_by(PromptVersion.version_number.desc()).limit(1))
        if not is_llm_retryable(item,run,result,config,prompt): raise ScreeningItemNotRetryable
        job=QueueRepository(db).enqueue(organization_id,"screening.llm_score_item",{"organization_id":str(organization_id),"screening_item_id":str(item.id),"screening_result_id":str(result.id),"config_id":str(config.id),"config_version":config.version,"prompt_version_id":str(prompt.id)},dedupe_key=f"llm-retry:{item.id}:{uuid.uuid4()}",trace_id=trace_id,max_attempts=3)
        item.llm_status="queued"; item.llm_safe_error_code=None; item.llm_started_at=None; item.llm_finished_at=None; item.finished_at=None
        run.finished_at=None
        aggregate_run(db,run); _audit_retry(db,item,actor_user_id,trace_id,"llm")
        db.flush(); return item,run,job
    if item.status!="failed" or item.safe_error_code not in RECOVERABLE_CODES: raise ScreeningItemNotRetryable
    if active_jobs: raise ScreeningRetryActive
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
    _audit_retry(db,item,actor_user_id,trace_id,"score" if parsed else "parse")
    db.flush(); return item,run,job

def apply_bulk_action(db,organization_id,run_id,payload,actor_user_id,trace_id):
    requested={item.item_id:item.expected_application_version for item in payload.items}
    relationships=list(db.execute(select(ScreeningItem.id,ScreeningItem.application_id,Application.candidate_id).join(Application,and_(Application.organization_id==ScreeningItem.organization_id,Application.id==ScreeningItem.application_id)).join(Candidate,and_(Candidate.organization_id==Application.organization_id,Candidate.id==Application.candidate_id)).where(ScreeningItem.organization_id==organization_id,ScreeningItem.run_id==run_id,ScreeningItem.id.in_(requested),Candidate.deleted_at.is_(None))))
    if len(relationships)!=len(requested): raise ScreeningBulkConflict
    expected_relationships={item_id:(application_id,candidate_id) for item_id,application_id,candidate_id in relationships}
    candidate_ids=sorted({candidate_id for _,candidate_id in expected_relationships.values()})
    try:
        for candidate_id in candidate_ids: lock_active_candidate(db,organization_id,candidate_id)
    except CandidateUnavailable:
        raise ScreeningBulkConflict from None
    run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==run_id).with_for_update())
    rows=list(db.scalars(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.run_id==run_id,ScreeningItem.id.in_(requested)).order_by(ScreeningItem.id).with_for_update()))
    if run is None or len(rows)!=len(requested): raise ScreeningBulkConflict
    if any(expected_relationships.get(item.id)!=(item.application_id,item.candidate_id) for item in rows): raise ScreeningBulkConflict
    if any(item.status!="scored" or item.application_id is None or not db.scalar(select(ScreeningResult.id).where(ScreeningResult.organization_id==organization_id,ScreeningResult.item_id==item.id)) for item in rows): raise ScreeningBulkConflict
    applications=list(db.scalars(select(Application).where(Application.organization_id==organization_id,Application.id.in_([item.application_id for item in rows])).order_by(Application.candidate_id,Application.id).with_for_update()))
    if len(applications)!=len(rows): raise ScreeningBulkConflict
    application_candidates={application.id:application.candidate_id for application in applications}
    if any(application_candidates.get(application_id)!=candidate_id for application_id,candidate_id in expected_relationships.values()): raise ScreeningBulkConflict
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
        if result=="applied": application=transition_application_record(db,organization_id,application.id,target,expected_version=application.version,actor_user_id=actor_user_id,trace_id=trace_id,reason_code=payload.reason_code,reason_text=payload.reason_text)
        output.append({"id":str(application.id),"stage":application.stage,"version":application.version,"result":result})
    db.flush(); return {"command":payload.command,"applied_count":sum(item["result"]=="applied" for item in output),"already_applied_count":sum(item["result"]=="already_applied" for item in output),"applications":output}
