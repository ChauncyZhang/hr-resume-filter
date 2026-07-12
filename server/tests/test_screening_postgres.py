import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from server.app.screening.models import CandidateDuplicateHint, ScreeningItem, ScreeningResult, ScreeningRun
from server.app.screening.service import InvalidScreeningTransition, transition_item, transition_run

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")

@pytest.fixture
def screening_db():
    url = os.environ["POSTGRES_SMOKE_URL"]; env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    with engine.begin() as connection: connection.execute(text("TRUNCATE screening_results, candidate_duplicate_hints, screening_items, screening_runs, organizations CASCADE"))
    yield engine; engine.dispose()

def seed(session: Session, slug: str):
    org, user, job, jd, rule, file = [uuid.uuid4() for _ in range(6)]
    session.execute(text("INSERT INTO organizations(id,slug,name,status,created_at,updated_at) VALUES(:o,:s,:s,'active',now(),now())"), {"o": org, "s": slug})
    session.execute(text("INSERT INTO users(id,organization_id,email,normalized_email,display_name,password_hash,status,authorization_version,created_at,updated_at) VALUES(:u,:o,:e,:e,'User','x','active',1,now(),now())"), {"u": user,"o":org,"e":f"{slug}@example.test"})
    session.execute(text("INSERT INTO jobs(id,organization_id,title,status,owner_id,headcount,priority,version,created_at,updated_at) VALUES(:j,:o,'Job','draft',:u,1,'normal',1,now(),now())"), {"j":job,"o":org,"u":user})
    for table, version_id in (("job_jd_versions",jd),("screening_rule_versions",rule)):
        session.execute(text(f"INSERT INTO {table}(id,organization_id,job_id,version_number,content,created_by,created_at) VALUES(:id,:o,:j,1,'{{}}',:u,now())"), {"id":version_id,"o":org,"j":job,"u":user})
    session.execute(text("INSERT INTO file_objects(id,organization_id,storage_key,original_filename,mime_type,size_bytes,sha256,uploaded_by,created_at) VALUES(:f,:o,:k,'x.txt','text/plain',1,:h,:u,now())"), {"f":file,"o":org,"k":f"{slug}/x","h":"0"*64,"u":user})
    return org,user,job,jd,rule,file

def make_run(session, ids):
    org,user,job,jd,rule,_ = ids
    run = ScreeningRun(organization_id=org, job_id=job, jd_version_id=jd, rule_version_id=rule, source="upload", status="queued", total_count=1, processed_count=0, succeeded_count=0, failed_count=0, created_by=user)
    session.add(run); session.flush(); return run

def test_run_item_transitions_counters_and_immutable_versions(screening_db) -> None:
    with Session(screening_db) as session:
        ids=seed(session,"states"); run=make_run(session,ids); item=ScreeningItem(organization_id=ids[0],run_id=run.id,file_object_id=ids[5],status="queued",attempts=0); session.add(item); session.commit()
        transition_run(run,"parsing"); transition_item(item,"parsing"); transition_item(item,"parsed"); session.commit()
        with pytest.raises(InvalidScreeningTransition): transition_run(run,"completed")
        run_id=run.id
        with pytest.raises(DBAPIError): session.execute(text("UPDATE screening_runs SET jd_version_id=:x WHERE id=:id"), {"x":uuid.uuid4(),"id":run_id})
        session.rollback()
    with Session(screening_db) as session:
        with pytest.raises(DBAPIError): session.execute(text("UPDATE screening_runs SET processed_count=1,succeeded_count=0,failed_count=0 WHERE id=:id"), {"id":run_id})

def test_results_are_append_only_except_human_override(screening_db) -> None:
    with Session(screening_db) as session:
        ids=seed(session,"results"); run=make_run(session,ids); item=ScreeningItem(organization_id=ids[0],run_id=run.id,file_object_id=ids[5],status="scored",attempts=1); session.add(item); session.flush()
        result=ScreeningResult(organization_id=ids[0],item_id=item.id,rule_engine_version="rule-v1",rule_score=85,recommendation="优先沟通",required_hits=["Python"],required_missing=[],bonus_hits=[],estimated_years=5,risks=[],questions=[]); session.add(result); session.commit()
        result.human_override_recommendation="可沟通"; result.human_override_reason_code="manual_review"; session.commit()
        with pytest.raises(DBAPIError): session.execute(text("UPDATE screening_results SET rule_score=1 WHERE id=:id"), {"id":result.id}); session.rollback()
        with pytest.raises(DBAPIError): session.execute(text("DELETE FROM screening_results WHERE id=:id"), {"id":result.id})

def test_tenant_fks_uniqueness_and_duplicate_hints(screening_db) -> None:
    with Session(screening_db) as session:
        left=seed(session,"left"); right=seed(session,"right"); run=make_run(session,left); session.commit()
        with pytest.raises(IntegrityError):
            session.add(ScreeningItem(organization_id=right[0],run_id=run.id,file_object_id=right[5],status="queued",attempts=0)); session.commit()
        session.rollback(); hint=CandidateDuplicateHint(organization_id=left[0],file_object_id=left[5],signals={"sha256":True},status="pending"); session.add(hint); session.commit(); assert hint.id
        other_job, other_jd, other_rule = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        session.execute(text("INSERT INTO jobs(id,organization_id,title,status,owner_id,headcount,priority,version,created_at,updated_at) VALUES(:j,:o,'Other','draft',:u,1,'normal',1,now(),now())"), {"j":other_job,"o":left[0],"u":left[1]})
        for table, version_id in (("job_jd_versions",other_jd),("screening_rule_versions",other_rule)):
            session.execute(text(f"INSERT INTO {table}(id,organization_id,job_id,version_number,content,created_by,created_at) VALUES(:id,:o,:j,1,'{{}}',:u,now())"), {"id":version_id,"o":left[0],"j":other_job,"u":left[1]})
        session.commit()
        with pytest.raises(IntegrityError):
            session.add(ScreeningRun(organization_id=left[0],job_id=left[2],jd_version_id=other_jd,rule_version_id=other_rule,source="upload",status="queued",total_count=0,processed_count=0,succeeded_count=0,failed_count=0,created_by=left[1])); session.commit()

def test_screening_indexes_and_constraints_exist(screening_db) -> None:
    inspector=inspect(screening_db)
    indexes={i["name"]:i["column_names"] for table in ("screening_runs","screening_items","candidate_duplicate_hints") for i in inspector.get_indexes(table)}
    assert indexes["ix_screening_runs_status"][:2]==["organization_id","status"]
    assert indexes["ix_screening_items_progress"][:3]==["organization_id","run_id","status"]
    assert indexes["ix_duplicate_hints_lookup"][0]=="organization_id"
    assert {c["name"] for c in inspector.get_check_constraints("screening_runs")} >= {"ck_screening_runs_status","ck_screening_runs_counts"}
