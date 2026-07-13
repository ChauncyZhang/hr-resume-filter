import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect,text

from server.tests.test_interview_persistence_postgres import _seed_application


TABLES = {"organizations", "departments", "users", "user_roles", "user_sessions", "jobs", "job_collaborators", "audit_logs", "candidates", "candidate_contacts", "file_objects", "resumes", "job_jd_versions", "screening_rule_versions", "applications", "application_stage_events", "candidate_notes", "candidate_events", "download_tickets", "idempotency_records", "background_jobs", "job_attempts", "outbox_events", "queue_claim_cursors", "screening_runs", "screening_items", "screening_results", "candidate_duplicate_hints", "llm_provider_configs", "prompt_versions", "llm_invocations", "llm_screening_evaluations", "interviews", "interview_participants", "interview_events", "interview_feedbacks", "interview_feedback_revisions"}


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


@pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")
def test_0013_backfills_stable_calendar_contacts_for_existing_interviews() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    env = {**os.environ, "DATABASE_URL": url}
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "downgrade", "base"], check=True, env=env)
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "0012_interviews_feedback"], check=True, env=env)
    with engine.begin() as connection:
        identifiers = _seed_application(connection)
        interview_id = uuid.uuid4()
        starts_at = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
        connection.execute(
            text(
                """
                INSERT INTO interviews(
                  id, organization_id, application_id, round_name, method, timezone,
                  starts_at, ends_at, status, notification_status, invitation_status,
                  owner_id, created_by, version, calendar_sequence, created_at, updated_at
                ) VALUES (
                  :id, :organization, :application, 'First round', 'video', 'Asia/Shanghai',
                  :starts_at, :ends_at, 'scheduled', 'not_sent', 'artifact_ready',
                  :owner, :owner, 1, 0, now(), now()
                )
                """
            ),
            {**identifiers, "id": interview_id, "starts_at": starts_at, "ends_at": starts_at + timedelta(minutes=45)},
        )
        connection.execute(
            text(
                """
                INSERT INTO interview_participants(
                  id, organization_id, interview_id, user_id, role, required_feedback,
                  attendance_status, task_status, created_at, updated_at
                ) VALUES (
                  :id, :organization, :interview, :interviewer, 'interviewer', true,
                  'invited', 'ready', now(), now()
                )
                """
            ),
            {**identifiers, "id": uuid.uuid4(), "interview": interview_id},
        )

    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    with engine.connect() as connection:
        snapshot = connection.execute(
            text(
                """
                SELECT calendar_organizer ->> 'email', calendar_attendees -> 0 ->> 'email'
                FROM interviews WHERE id = :id
                """
            ),
            {"id": interview_id},
        ).one()
        assert snapshot == ("owner@test", "interviewer@test")
    engine.dispose()
