import asyncio,hashlib,os,subprocess,uuid
import pytest
from sqlalchemy import func,select,text
from server.app.core.settings import Settings
from server.app.identity.models import Job,Organization,User,UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.queue.models import BackgroundJob
from server.app.queue.repository import QueueRepository
from server.app.queue.runtime import DatabaseQueueGateway
from server.app.recruiting.models import ApplicationReviewTask,FileObject,JobJdVersion,ScreeningRuleVersion
from server.app.screening.models import ScreeningItem,ScreeningRun
from server.app.screening.terminal import finalize_screening_dead_letter,screening_terminal_callbacks
from server.app.worker.main import Worker
from server.tests.test_screening_api import Probe

pytestmark=pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"),reason="PostgreSQL smoke URL not configured")
def test_unexpected_parse_and_score_exhaustion_atomically_finalize_domain_facts():
    url=os.environ["POSTGRES_SMOKE_URL"]; subprocess.run(["python","-m","alembic","-c","server/alembic.ini","upgrade","head"],check=True,env={**os.environ,"DATABASE_URL":url}); app=create_app(settings=Settings(environment="test",database_url=url,cors_origins=["https://hr.example.test"]),database_probe=Probe(),storage_probe=Probe(),quarantine_storage=object())
    with app.state.identity_store.sync_session() as db:
        db.execute(text("TRUNCATE organizations CASCADE")); org=Organization(slug="dead",name="Dead",status="active"); user=User(organization=org,email="dead@test",normalized_email="dead@test",display_name="Dead",password_hash=PasswordService().hash("correct")); user.roles.append(UserRole(role="recruiting_admin")); db.add(user); db.flush(); job=Job(organization_id=org.id,title="Dead",owner_id=user.id,status="draft"); db.add(job); db.flush(); jd=JobJdVersion(organization_id=org.id,job_id=job.id,version_number=1,content={"text":"required: Python"},created_by=user.id); rule=ScreeningRuleVersion(organization_id=org.id,job_id=job.id,version_number=1,content={},created_by=user.id); db.add_all([jd,rule]); db.flush(); run=ScreeningRun(organization_id=org.id,job_id=job.id,jd_version_id=jd.id,rule_version_id=rule.id,source="upload",status="parsing",total_count=2,processed_count=0,succeeded_count=0,failed_count=0,created_by=user.id); db.add(run); db.flush(); items=[]
        for index,status in enumerate(("parsing","parsed")):
            data=b"Python"; file=FileObject(organization_id=org.id,storage_key=f"clean/{org.id}/{uuid.uuid4()}",original_filename=f"{index}.txt",mime_type="text/plain",size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),uploaded_by=user.id,storage_state="clean",detected_type="txt",scan_status="clean"); db.add(file); db.flush(); item=ScreeningItem(organization_id=org.id,run_id=run.id,file_object_id=file.id,status=status,attempts=1); db.add(item); db.flush(); items.append(item)
        repo=QueueRepository(db); parse=repo.enqueue(org.id,"screening.parse_item",{"organization_id":str(org.id),"screening_item_id":str(items[0].id),"parser_version":"parser-v1"},dedupe_key="dead-parse",max_attempts=1); score=repo.enqueue(org.id,"screening.score_item",{"organization_id":str(org.id),"screening_item_id":str(items[1].id),"jd_version_id":str(jd.id),"rule_version_id":str(rule.id),"rule_engine_version":"rule-v1"},dedupe_key="dead-score",max_attempts=1); db.commit(); org_id,run_id,item_ids,job_ids=org.id,run.id,[item.id for item in items],[parse.id,score.id]
    async def explode(_): raise RuntimeError("private resume body")
    worker=Worker(Probe(),Probe(),interval_seconds=0,queue=DatabaseQueueGateway(url,terminal_callbacks=screening_terminal_callbacks()),handlers={"screening.parse_item":explode,"screening.score_item":explode},outbox_handlers={},worker_id="dead-worker",lease_seconds=30,heartbeat_seconds=10)
    asyncio.run(worker._poll_once()); asyncio.run(worker._poll_once())
    with app.state.identity_store.sync_session() as db:
        assert set(db.scalars(select(BackgroundJob.status).where(BackgroundJob.id.in_(job_ids))))=={"dead_letter"}; stored=[db.get(ScreeningItem,item_id) for item_id in item_ids]; aggregate=db.get(ScreeningRun,run_id); assert all(item.status=="failed" and item.finished_at and item.safe_error_code=="handler_failed" for item in stored); assert aggregate.status=="failed" and aggregate.processed_count==2 and aggregate.failed_count==2
        assert db.scalar(select(func.count(ApplicationReviewTask.id)))==0
        for job_id in job_ids: finalize_screening_dead_letter(db,db.get(BackgroundJob,job_id),"handler_failed",db.get(BackgroundJob,job_id).updated_at)
        db.commit(); assert db.get(ScreeningRun,run_id).processed_count==2
