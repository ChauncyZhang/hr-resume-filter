import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect,text


TABLES = {"organizations", "departments", "users", "user_roles", "user_sessions", "jobs", "job_collaborators", "audit_logs", "candidates", "candidate_contacts", "file_objects", "resumes", "job_jd_versions", "screening_rule_versions", "applications", "application_stage_events", "candidate_notes", "candidate_events", "download_tickets", "idempotency_records", "background_jobs", "job_attempts", "outbox_events", "queue_claim_cursors", "screening_runs", "screening_items", "screening_results", "candidate_duplicate_hints", "llm_provider_configs", "prompt_versions", "llm_invocations", "llm_screening_evaluations"}


@pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")
def test_migration_upgrades_and_downgrades_empty_baseline() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    sync_url = url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    assert TABLES <= set(inspect(engine).get_table_names())
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "downgrade", "base"], check=True, env=env)
    assert not (TABLES & set(inspect(engine).get_table_names()))


@pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")
def test_0010_backfills_and_downgrades_data_bearing_0009() -> None:
    url=os.environ["POSTGRES_SMOKE_URL"]; env={**os.environ,"DATABASE_URL":url}; sync_url=url.replace("+asyncpg","+psycopg"); engine=create_engine(sync_url)
    subprocess.run(["python","-m","alembic","-c","server/alembic.ini","upgrade","0009_llm_gateway_foundation"],check=True,env=env)
    ids={name:uuid.uuid4() for name in ("org","user","job","jd","rule","file","run","item")}
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations(id,slug,name,status,created_at,updated_at) VALUES(:org,'migration-data','Migration','active',now(),now())"),ids)
        connection.execute(text("INSERT INTO users(id,organization_id,email,normalized_email,display_name,password_hash,status,authorization_version,created_at,updated_at) VALUES(:user,:org,'migration@test','migration@test','Migration','x','active',1,now(),now())"),ids)
        connection.execute(text("INSERT INTO jobs(id,organization_id,title,status,owner_id,headcount,priority,version,created_at,updated_at) VALUES(:job,:org,'Job','draft',:user,1,'normal',1,now(),now())"),ids)
        connection.execute(text("INSERT INTO job_jd_versions(id,organization_id,job_id,version_number,content,created_by,created_at) VALUES(:jd,:org,:job,1,'{}',:user,now())"),ids); connection.execute(text("INSERT INTO screening_rule_versions(id,organization_id,job_id,version_number,content,created_by,created_at) VALUES(:rule,:org,:job,1,'{}',:user,now())"),ids)
        connection.execute(text("INSERT INTO file_objects(id,organization_id,storage_key,original_filename,mime_type,size_bytes,sha256,uploaded_by,created_at) VALUES(:file,:org,'migration/x','x.txt','text/plain',1,repeat('0',64),:user,now())"),ids)
        connection.execute(text("INSERT INTO screening_runs(id,organization_id,job_id,jd_version_id,rule_version_id,source,status,total_count,processed_count,succeeded_count,failed_count,created_by,version,created_at,updated_at) VALUES(:run,:org,:job,:jd,:rule,'upload','rule_scoring',1,0,0,0,:user,1,now(),now())"),ids)
        connection.execute(text("INSERT INTO screening_items(id,organization_id,run_id,file_object_id,status,attempts,created_at,updated_at) VALUES(:item,:org,:run,:file,'parsed',1,now(),now())"),ids)
    subprocess.run(["python","-m","alembic","-c","server/alembic.ini","upgrade","0010_llm_screening_evaluations"],check=True,env=env)
    with engine.connect() as connection: assert connection.execute(text("SELECT llm_status,llm_attempts FROM screening_items WHERE id=:item"),ids).one()==("not_requested",0)
    subprocess.run(["python","-m","alembic","-c","server/alembic.ini","downgrade","0009_llm_gateway_foundation"],check=True,env=env)
    columns={column["name"] for column in inspect(engine).get_columns("screening_items")}; assert "llm_status" not in columns
    with engine.connect() as connection: assert connection.scalar(text("SELECT count(*) FROM screening_items WHERE id=:item"),ids)==1
    engine.dispose()
