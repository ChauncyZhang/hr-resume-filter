import asyncio,io,uuid
from dataclasses import dataclass,field
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import func,select

from server.app.recruiting.models import Application,Candidate,FileObject,Resume
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.pipeline import ScreeningPipeline
from server.app.screening.scanner import ScanResult
from server.app.queue.service import PermanentJobError,RetryableJobError
import pytest
from server.tests.test_screening_api import app_and_seed,login

@dataclass
class MemoryPipelineStorage:
    objects:dict[str,bytes]=field(default_factory=dict); calls:list[str]=field(default_factory=list); delete_ok:bool=True
    async def open(self,key,max_bytes): self.calls.append("open"); return io.BytesIO(self.objects[key])
    async def copy(self,source,target,max_bytes): self.calls.append("copy"); self.objects[target]=self.objects[source]
    async def delete(self,key): self.calls.append("delete"); self.objects.pop(key,None) if self.delete_ok else None; return self.delete_ok

class Scanner:
    def __init__(self,result=ScanResult.CLEAN): self.result=result; self.calls=[]
    async def scan(self,stream,max_bytes): self.calls.append("scan"); return self.result

def seeded_pipeline(tmp_path,text=b"required: Python\nPython 5 years",filename="Alice.txt",mime="text/plain"):
    app,upload_storage,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); run=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers={**headers,"Idempotency-Key":"run"}).json()["data"]
        item=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":(filename,text,mime)},headers={**headers,"Idempotency-Key":"item"}).json()["data"]
    storage=MemoryPipelineStorage(dict(upload_storage.objects)); scanner=Scanner(); pipeline=ScreeningPipeline(app.state.identity_store.sync_session,storage,scanner,app.state.settings)
    return app,pipeline,storage,scanner,SimpleNamespace(organization_id=next(iter(storage.objects)).split("/")[1],payload={"organization_id":next(iter(storage.objects)).split("/")[1],"screening_item_id":item["id"],"parser_version":"parser-v1"},attempts=1,max_attempts=3),run,item

def test_clean_parse_then_score_is_replay_safe_and_never_auto_advances(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path)
    asyncio.run(pipeline.parse_item(job)); asyncio.run(pipeline.parse_item(job))
    assert scanner.calls==["scan"] and storage.calls[:3]==["open","copy","delete"]
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); assert stored.status=="parsed" and stored.candidate_id and stored.resume_id and stored.application_id
        score_job=SimpleNamespace(organization_id=stored.organization_id,payload={"organization_id":str(stored.organization_id),"screening_item_id":str(stored.id),"jd_version_id":str(db.get(ScreeningRun,uuid.UUID(run["id"])).jd_version_id),"rule_version_id":str(db.get(ScreeningRun,uuid.UUID(run["id"])).rule_version_id),"rule_engine_version":"rule-v1"},attempts=1,max_attempts=3)
    asyncio.run(pipeline.score_item(score_job)); asyncio.run(pipeline.score_item(score_job))
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count(Candidate.id)))==1 and db.scalar(select(func.count(Resume.id)))==1 and db.scalar(select(func.count(Application.id)))==1 and db.scalar(select(func.count(ScreeningResult.id)))==1
        application=db.scalar(select(Application)); result=db.scalar(select(ScreeningResult)); completed=db.get(ScreeningRun,uuid.UUID(run["id"]))
        assert application.stage=="new" and application.source=="screening" and result.rule_score<=100 and completed.status=="completed" and completed.processed_count==1

def test_infected_is_terminal_without_parse_or_identity(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path); scanner.result=ScanResult.INFECTED
    asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db:
        assert db.get(ScreeningItem,uuid.UUID(item["id"])).safe_error_code=="malware_detected" and db.scalar(select(func.count(Candidate.id)))==0 and db.get(ScreeningRun,uuid.UUID(run["id"])).status=="failed"
    assert "copy" not in storage.calls

def test_clean_promotion_retains_cleanup_marker_when_source_delete_fails(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path); storage.delete_ok=False
    asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); file=db.get(__import__("server.app.recruiting.models",fromlist=["FileObject"]).FileObject,stored.file_object_id)
        assert file.storage_state=="clean" and file.quarantine_cleanup_key and file.quarantine_cleanup_key in storage.objects

def test_retryable_scan_failure_then_exhaustion_leaves_terminal_progress(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path); scanner.result=ScanResult.UNAVAILABLE
    with pytest.raises(RetryableJobError): asyncio.run(pipeline.parse_item(job))
    job.attempts=job.max_attempts
    with pytest.raises(PermanentJobError): asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db:
        stored=db.get(ScreeningItem,uuid.UUID(item["id"])); aggregate=db.get(ScreeningRun,uuid.UUID(run["id"]))
        assert stored.status=="failed" and stored.safe_error_code=="scanner_unavailable" and aggregate.status=="failed" and aggregate.processed_count==1

@pytest.mark.parametrize(("filename","mime","content","version"),[
    ("resume.txt","text/plain",b"Python","txt-v1"),
    ("resume.docx","application/vnd.openxmlformats-officedocument.wordprocessingml.document",__import__("server.tests.test_screening",fromlist=["docx_bytes"]).docx_bytes("Python"),"docx-v1"),
    ("resume.pdf","application/pdf",__import__("server.tests.test_screening",fromlist=["pdf_bytes"]).pdf_bytes(),"pdf-v1"),
])
def test_pipeline_parses_each_approved_document_type(tmp_path,filename,mime,content,version):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path,content,filename,mime); asyncio.run(pipeline.parse_item(job))
    with app.state.identity_store.sync_session() as db: assert db.get(ScreeningItem,uuid.UUID(item["id"])).parser_version==version

def test_run_aggregation_is_partial_for_mixed_terminal_facts(tmp_path):
    app,pipeline,storage,scanner,job,run,item=seeded_pipeline(tmp_path)
    with app.state.identity_store.sync_session() as db:
        first=db.get(ScreeningItem,uuid.UUID(item["id"])); aggregate=db.get(ScreeningRun,uuid.UUID(run["id"])); first.status="scored"; extra_file=FileObject(organization_id=first.organization_id,storage_key=f"quarantine/{first.organization_id}/{aggregate.id}/{uuid.uuid4()}",original_filename="failed.txt",mime_type="text/plain",size_bytes=1,sha256="0"*64,uploaded_by=aggregate.created_by,storage_state="rejected",detected_type="txt",scan_status="rejected"); db.add(extra_file); db.flush(); db.add(ScreeningItem(organization_id=first.organization_id,run_id=aggregate.id,file_object_id=extra_file.id,status="failed",safe_error_code="malware_detected",attempts=1)); aggregate.total_count=2; db.flush(); pipeline._aggregate(db,aggregate); db.commit()
        assert aggregate.status=="partial" and aggregate.processed_count==2 and aggregate.succeeded_count==1 and aggregate.failed_count==1
