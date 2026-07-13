import asyncio,uuid
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from server.app.queue.models import BackgroundJob
from server.app.queue.repository import QueueRepository
from server.app.recruiting.models import Application,ApplicationStageEvent,FileObject
from server.app.identity.models import AuditLog
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.actions import retry_screening_item
from server.tests.test_screening_api import login
from server.tests.test_screening_pipeline import seeded_pipeline

def failed_item(tmp_path,*,parsed=False,code="scanner_unavailable"):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path)
    if parsed: asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); aggregate=db.get(ScreeningRun,uuid.UUID(run["id"])); stored.status="failed"; stored.safe_error_code=code; stored.finished_at=stored.created_at; aggregate.status="failed"; aggregate.processed_count=aggregate.failed_count=1
        queued=list(db.scalars(select(BackgroundJob).where(BackgroundJob.organization_id==stored.organization_id)))
        if not queued: queued=[QueueRepository(db).enqueue(stored.organization_id,"screening.parse_item",{"organization_id":str(stored.organization_id),"screening_item_id":str(stored.id),"parser_version":"parser-v1"},dedupe_key=f"parse:{stored.id}")]
        for background in queued: background.status="dead_letter"; background.attempts=background.max_attempts
        db.commit()
    return app,run,item

def test_retry_parse_and_score_restore_progress_and_are_idempotent(tmp_path):
    for index,parsed in enumerate((False,True)):
        root=tmp_path/str(index); root.mkdir(); app,run,item=failed_item(root,parsed=parsed,code="scoring_failed" if parsed else "scanner_unavailable")
        with TestClient(app) as client:
            headers=login(client,"admin@example.test"); request={**headers,"Idempotency-Key":"retry"}; response=client.post(f"/api/v1/screening-items/{item['id']}/retry",headers=request); assert response.status_code==200; body=response.json()["data"]
            assert body["item"]["status"]==("parsed" if parsed else "queued") and body["item"]["retryable"] is False and body["run"]["processed_count"]==0
            replay=client.post(f"/api/v1/screening-items/{item['id']}/retry",headers=request); assert replay.json()==response.json()
        with app.state.identity_store.sync_session() as db:
            jobs=list(db.scalars(select(BackgroundJob).where(BackgroundJob.status=="queued"))); assert len(jobs)==1 and jobs[0].type==("screening.score_item" if parsed else "screening.parse_item")

def test_retry_service_enqueues_a_new_terminal_aware_attempt(tmp_path):
    app,run,item=failed_item(tmp_path)
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"]))
        retried,aggregate,job=retry_screening_item(db,stored.organization_id,stored.id,"a"*32)
        assert retried.status=="queued" and aggregate.processed_count==0 and job.status=="queued"

def test_retry_rejects_permanent_active_and_manager_scope(tmp_path):
    app,run,item=failed_item(tmp_path,code="malware_detected")
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); rejected=client.post(f"/api/v1/screening-items/{item['id']}/retry",headers={**headers,"Idempotency-Key":"retry"}); assert rejected.status_code==409 and rejected.json()["code"]=="screening_item_not_retryable"
        client.post("/api/v1/auth/logout",headers=headers); manager=login(client,"manager@example.test"); assert client.post(f"/api/v1/screening-items/{item['id']}/retry",headers={**manager,"Idempotency-Key":"manager"}).status_code==404

def test_retry_recomputes_stale_counters_and_rejects_unavailable_file(tmp_path):
    app,run,item=failed_item(tmp_path)
    with app.state.identity_store.sync_session() as db:
        aggregate=db.get(ScreeningRun,uuid.UUID(run["id"])); stored=db.get(ScreeningItem,uuid.UUID(item["id"])); file=db.get(FileObject,stored.file_object_id)
        aggregate.succeeded_count=1; aggregate.failed_count=0; aggregate.processed_count=1
        db.commit()
    with TestClient(app) as client:
        headers=login(client,"admin@example.test")
        response=client.post(f"/api/v1/screening-items/{item['id']}/retry",headers={**headers,"Idempotency-Key":"recompute"})
        assert response.status_code==200
        assert response.json()["data"]["run"]["processed_count"]==0
        assert response.json()["data"]["run"]["succeeded_count"]==0

    other=tmp_path/"deleted"; other.mkdir(); app,run,item=failed_item(other)
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); file=db.get(FileObject,stored.file_object_id); file.storage_state="deleted"; db.commit()
    with TestClient(app) as client:
        headers=login(client,"admin@example.test")
        response=client.post(f"/api/v1/screening-items/{item['id']}/retry",headers={**headers,"Idempotency-Key":"deleted"})
        assert response.status_code==409 and response.json()["code"]=="screening_item_not_retryable"

def scored_item(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path); asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); aggregate=db.get(ScreeningRun,uuid.UUID(run["id"])); score=type("Job",(),{"payload":{"organization_id":str(stored.organization_id),"screening_item_id":str(stored.id),"jd_version_id":str(aggregate.jd_version_id),"rule_version_id":str(aggregate.rule_version_id),"rule_engine_version":"rule-v1"},"attempts":1,"max_attempts":3})()
    asyncio.run(pipeline.score_item(score)); return app,run,item

def test_bulk_advance_is_atomic_versioned_and_does_not_duplicate_evidence(tmp_path):
    app,run,item=scored_item(tmp_path)
    with app.state.identity_store.sync_session() as db: application=db.get(Application,db.get(ScreeningItem,uuid.UUID(item["id"])).application_id); application_id,version=application.id,application.version
    payload={"command":"advance_to_review","items":[{"item_id":item["id"],"expected_application_version":version}]}
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); first=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json=payload,headers={**headers,"Idempotency-Key":"bulk"}); assert first.status_code==200 and first.json()["data"]["applied_count"]==1
        replay=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json=payload,headers={**headers,"Idempotency-Key":"bulk"}); assert replay.json()==first.json()
        again=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json=payload,headers={**headers,"Idempotency-Key":"bulk-new"}); assert again.status_code==200 and again.json()["data"]["already_applied_count"]==1
    with app.state.identity_store.sync_session() as db:
        assert db.get(Application,application_id).stage=="review" and db.scalar(select(func.count(ApplicationStageEvent.id)))==1 and db.scalar(select(func.count(AuditLog.id)).where(AuditLog.event_type=="application.stage_changed"))==1

def test_bulk_reject_validation_and_all_or_nothing_stale_version(tmp_path):
    app,run,item=scored_item(tmp_path)
    with app.state.identity_store.sync_session() as db: application=db.get(Application,db.get(ScreeningItem,uuid.UUID(item["id"])).application_id); version=application.version
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); missing=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json={"command":"reject","items":[{"item_id":item["id"],"expected_application_version":version}]},headers={**headers,"Idempotency-Key":"missing"}); assert missing.status_code==422
        stale=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json={"command":"advance_to_review","items":[{"item_id":item["id"],"expected_application_version":version+1}]},headers={**headers,"Idempotency-Key":"stale"}); assert stale.status_code==409
    with app.state.identity_store.sync_session() as db: assert db.get(Application,application.id).stage=="new" and db.scalar(select(func.count(ApplicationStageEvent.id)))==0

def test_bulk_reject_persists_human_reason_without_audit_text(tmp_path):
    app,run,item=scored_item(tmp_path)
    with app.state.identity_store.sync_session() as db:
        application=db.get(Application,db.get(ScreeningItem,uuid.UUID(item["id"])).application_id); application_id,version=application.id,application.version
    reason="候选人明确表示暂不考虑该岗位"
    payload={"command":"reject","reason_code":"candidate_declined","reason_text":reason,"items":[{"item_id":item["id"],"expected_application_version":version}]}
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); response=client.post(f"/api/v1/screening-runs/{run['id']}/bulk-actions",json=payload,headers={**headers,"Idempotency-Key":"reject"}); assert response.status_code==200
    with app.state.identity_store.sync_session() as db:
        assert db.get(Application,application_id).human_conclusion==reason
        audit=db.scalar(select(AuditLog).where(AuditLog.event_type=="application.stage_changed")); assert reason not in str(audit.metadata_json)
