import asyncio,hashlib,os,subprocess,uuid
from types import SimpleNamespace
import pytest
from sqlalchemy import func,select,text
from server.app.core.settings import Settings
from server.app.identity.models import Job,Organization,User,UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import Application,Candidate,FileObject,JobJdVersion,Resume,ScreeningRuleVersion
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.pipeline import ScreeningPipeline
from server.tests.test_screening_api import Probe
from server.tests.test_screening_pipeline import MemoryPipelineStorage,Scanner

pytestmark=pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"),reason="PostgreSQL smoke URL not configured")
def test_postgres_100_item_restart_replay_has_no_duplicates_or_lost_progress():
    url=os.environ["POSTGRES_SMOKE_URL"]; subprocess.run(["python","-m","alembic","-c","server/alembic.ini","upgrade","head"],check=True,env={**os.environ,"DATABASE_URL":url}); app=create_app(settings=Settings(environment="test",database_url=url,cors_origins=["https://hr.example.test"]),database_probe=Probe(),storage_probe=Probe(),quarantine_storage=object()); storage=MemoryPipelineStorage(); scanner=Scanner()
    with app.state.identity_store.sync_session() as db:
        db.execute(text("TRUNCATE organizations CASCADE")); org=Organization(slug="bulk",name="Bulk",status="active"); user=User(organization=org,email="bulk@test",normalized_email="bulk@test",display_name="Bulk",password_hash=PasswordService().hash("correct")); user.roles.append(UserRole(role="recruiting_admin")); db.add(user); db.flush(); job=Job(organization_id=org.id,title="Bulk",owner_id=user.id,status="draft"); db.add(job); db.flush(); jd=JobJdVersion(organization_id=org.id,job_id=job.id,version_number=1,content={"text":"required: Python"},created_by=user.id); rule=ScreeningRuleVersion(organization_id=org.id,job_id=job.id,version_number=1,content={},created_by=user.id); db.add_all([jd,rule]); db.flush(); run=ScreeningRun(organization_id=org.id,job_id=job.id,jd_version_id=jd.id,rule_version_id=rule.id,source="upload",status="parsing",total_count=100,processed_count=0,succeeded_count=0,failed_count=0,created_by=user.id); db.add(run); db.flush(); item_ids=[]
        for index in range(100):
            data=f"Python {index%10} years".encode(); file=FileObject(organization_id=org.id,storage_key=f"quarantine/{org.id}/{run.id}/{uuid.uuid4()}",original_filename=f"candidate-{index}.txt",mime_type="text/plain",size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),uploaded_by=user.id,storage_state="quarantine",detected_type="txt",scan_status="pending"); db.add(file); db.flush(); item=ScreeningItem(organization_id=org.id,run_id=run.id,file_object_id=file.id,status="queued",attempts=0); db.add(item); db.flush(); item_ids.append(item.id); storage.objects[file.storage_key]=data
        db.commit(); org_id,run_id,jd_id,rule_id=org.id,run.id,jd.id,rule.id
    pipeline=ScreeningPipeline(app.state.identity_store.sync_session,storage,scanner,app.state.settings)
    async def process():
        for index,item_id in enumerate(item_ids):
            parse=SimpleNamespace(payload={"organization_id":str(org_id),"screening_item_id":str(item_id),"parser_version":"parser-v1"},attempts=1,max_attempts=3,trace_id="bulk")
            await pipeline.parse_item(parse)
            if index<10: await pipeline.parse_item(parse)
            score=SimpleNamespace(payload={"organization_id":str(org_id),"screening_item_id":str(item_id),"jd_version_id":str(jd_id),"rule_version_id":str(rule_id),"rule_engine_version":"rule-v1"},attempts=1,max_attempts=3)
            await pipeline.score_item(score)
            if index<10: await pipeline.score_item(score)
    asyncio.run(process())
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count(Candidate.id)))==100 and db.scalar(select(func.count(Resume.id)))==100 and db.scalar(select(func.count(Application.id)))==100 and db.scalar(select(func.count(ScreeningResult.id)))==100
        completed=db.get(ScreeningRun,run_id); assert completed.status=="completed" and completed.processed_count==100 and completed.succeeded_count==100 and completed.failed_count==0
        assert set(db.scalars(select(Application.stage)))=={"new"}
