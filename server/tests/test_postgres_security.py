from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timezone
import os
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from server.app.identity.models import Organization, User, UserStatus
from server.app.identity.security import PasswordService
from server.app.identity.service import AuthenticationFailed, Clock, IdentityService, TokenSource
from server.app.identity.store import IdentityStore


pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")


@pytest.fixture
def pg_store():
    url = os.environ["POSTGRES_SMOKE_URL"]
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    store = IdentityStore(url)
    yield store
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "downgrade", "base"], check=True, env=env)


def seed_pg_user(store):
    with store.sync_session() as db:
        organization = Organization(slug="concurrent", name="Concurrent", status="active")
        user = User(organization=organization, email="user@example.test", normalized_email="user@example.test", display_name="User", password_hash=PasswordService().hash("correct"), status=UserStatus.ACTIVE)
        db.add(user)
        db.commit()
        return user.id, organization.id


def test_five_concurrent_failures_reliably_lock_account(pg_store) -> None:
    user_id, _ = seed_pg_user(pg_store)

    def fail_login(_):
        service = IdentityService(pg_store, Clock(), TokenSource())
        with pytest.raises(AuthenticationFailed):
            service.login("concurrent", "user@example.test", "wrong", trace_id=str(uuid4()), network="proxy")

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(fail_login, range(5)))
    with pg_store.sync_session() as db:
        user = db.get(User, user_id)
        assert user.failed_login_count == 5
        assert user.locked_until > datetime.now(timezone.utc)


def test_concurrent_success_cannot_overwrite_failed_attempt(pg_store) -> None:
    user_id, _ = seed_pg_user(pg_store)

    def login(password):
        service = IdentityService(pg_store, Clock(), TokenSource())
        try:
            service.login("concurrent", "user@example.test", password, trace_id=str(uuid4()), network="proxy")
        except AuthenticationFailed:
            pass

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(login, ["correct", "wrong"]))
    with pg_store.sync_session() as db:
        user = db.get(User, user_id)
        assert user.failed_login_count in {0, 1}
        assert db.execute(text("select count(*) from audit_logs where event_type='authentication.login'")).scalar_one() == 2


def test_independent_users_in_one_organization_do_not_share_login_lock(pg_store) -> None:
    first_id, organization_id = seed_pg_user(pg_store)
    with pg_store.sync_session() as db:
        second = User(organization_id=organization_id, email="second@example.test", normalized_email="second@example.test", display_name="Second", password_hash=PasswordService().hash("correct"), status=UserStatus.ACTIVE)
        db.add(second)
        db.commit()
        assert second.id != first_id

    barrier = Barrier(2, timeout=5)

    class BarrierPasswords:
        def verify(self, encoded, password):
            barrier.wait()
            return False

    def fail(email):
        service = IdentityService(pg_store, Clock(), TokenSource())
        service.passwords = BarrierPasswords()
        with pytest.raises(AuthenticationFailed):
            service.login("concurrent", email, "wrong", trace_id=str(uuid4()), network="proxy")

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(fail, ["user@example.test", "second@example.test"]))


def test_cross_organization_relationships_are_rejected(pg_store) -> None:
    with pg_store.engine.begin() as connection:
        org1, org2, dep1, user1, user2, job1 = [uuid4() for _ in range(6)]
        now = datetime.now(timezone.utc)
        connection.execute(text("insert into organizations(id,slug,name,status,created_at,updated_at) values (:id,'o1','O1','active',:n,:n),(:id2,'o2','O2','active',:n,:n)"), {"id": org1, "id2": org2, "n": now})
        connection.execute(text("insert into departments(id,organization_id,name,created_at,updated_at) values (:id,:org,'D',:n,:n)"), {"id": dep1, "org": org1, "n": now})
        password = PasswordService().hash("x")
        connection.execute(text("insert into users(id,organization_id,email,normalized_email,display_name,password_hash,status,authorization_version,failed_login_count,created_at,updated_at) values (:u1,:o1,'a@x','a@x','A',:p,'ACTIVE',1,0,:n,:n),(:u2,:o2,'b@x','b@x','B',:p,'ACTIVE',1,0,:n,:n)"), {"u1": user1, "u2": user2, "o1": org1, "o2": org2, "p": password, "n": now})
        connection.execute(text("insert into jobs(id,organization_id,title,owner_id,status,created_at,updated_at) values (:j,:o1,'J',:u1,'draft',:n,:n)"), {"j": job1, "o1": org1, "u1": user1, "n": now})
    invalid = [
        ("insert into users(id,organization_id,department_id,email,normalized_email,display_name,password_hash,status,authorization_version,failed_login_count,created_at,updated_at) values (:id,:o2,:d,'c@x','c@x','C','x','ACTIVE',1,0,now(),now())", {"id": uuid4(), "o2": org2, "d": dep1}),
        ("insert into jobs(id,organization_id,title,owner_id,status,created_at,updated_at) values (:id,:o2,'bad',:u1,'draft',now(),now())", {"id": uuid4(), "o2": org2, "u1": user1}),
        ("insert into job_collaborators(id,organization_id,job_id,user_id,access_role,created_at,updated_at) values (:id,:o2,:j,:u2,'job_recruiter',now(),now())", {"id": uuid4(), "o2": org2, "j": job1, "u2": user2}),
        ("insert into job_collaborators(id,organization_id,job_id,user_id,access_role,created_at,updated_at) values (:id,:o1,:j,:u2,'job_recruiter',now(),now())", {"id": uuid4(), "o1": org1, "j": job1, "u2": user2}),
        ("insert into departments(id,organization_id,parent_id,name,created_at,updated_at) values (:id,:o2,:d,'bad',now(),now())", {"id": uuid4(), "o2": org2, "d": dep1}),
    ]
    for statement, params in invalid:
        with pytest.raises(IntegrityError):
            with pg_store.engine.begin() as connection:
                connection.execute(text(statement), params)


def test_audit_logs_reject_update_and_delete(pg_store) -> None:
    _, organization_id = seed_pg_user(pg_store)
    with pg_store.engine.begin() as connection:
        audit_id = uuid4()
        connection.execute(text("insert into audit_logs(id,organization_id,event_type,outcome,metadata_json,created_at) values (:id,:org,'test','success','{}',now())"), {"id": audit_id, "org": organization_id})
    for statement in ("update audit_logs set outcome='changed' where id=:id", "delete from audit_logs where id=:id"):
        with pytest.raises(OperationalError):
            with pg_store.engine.begin() as connection:
                connection.execute(text(statement), {"id": audit_id})


def test_active_application_partial_index_and_recruiting_tenant_constraints(pg_store) -> None:
    user_id, organization_id = seed_pg_user(pg_store)
    with pg_store.engine.begin() as connection:
        candidate, job, file_id, resume = [uuid4() for _ in range(4)]
        connection.execute(text("insert into candidates(id,organization_id,display_name,owner_id) values (:id,:org,'Masked Candidate',:user)"), {"id": candidate, "org": organization_id, "user": user_id})
        connection.execute(text("insert into jobs(id,organization_id,title,owner_id,status,created_at,updated_at) values (:id,:org,'Role',:user,'open',now(),now())"), {"id": job, "org": organization_id, "user": user_id})
        connection.execute(text("insert into file_objects(id,organization_id,storage_key,original_filename,mime_type,size_bytes,sha256,uploaded_by) values (:id,:org,'private/key','resume.pdf','application/pdf',1,:sha,:user)"), {"id": file_id, "org": organization_id, "sha": "0" * 64, "user": user_id})
        connection.execute(text("insert into resumes(id,organization_id,candidate_id,file_object_id,version_number) values (:id,:org,:candidate,:file,1)"), {"id": resume, "org": organization_id, "candidate": candidate, "file": file_id})
        values = {"id": uuid4(), "org": organization_id, "candidate": candidate, "job": job, "resume": resume, "user": user_id}
        connection.execute(text("insert into applications(id,organization_id,candidate_id,job_id,resume_id,owner_id,stage) values (:id,:org,:candidate,:job,:resume,:user,'new')"), values)
    with pytest.raises(IntegrityError):
        with pg_store.engine.begin() as connection:
            connection.execute(text("insert into applications(id,organization_id,candidate_id,job_id,resume_id,owner_id,stage) values (:id,:org,:candidate,:job,:resume,:user,'review')"), {**values, "id": uuid4()})
    with pg_store.engine.begin() as connection:
        connection.execute(text("update applications set stage='rejected' where id=:id"), values)
        connection.execute(text("insert into applications(id,organization_id,candidate_id,job_id,resume_id,owner_id,stage,source_application_id) values (:new,:org,:candidate,:job,:resume,:user,'new',:id)"), {**values, "new": uuid4()})


def test_recruiting_immutable_rows_reject_update_and_delete(pg_store) -> None:
    user_id, organization_id = seed_pg_user(pg_store)
    with pg_store.engine.begin() as connection:
        job_id = uuid4()
        version_id = uuid4()
        connection.execute(text("insert into jobs(id,organization_id,title,owner_id,status,created_at,updated_at) values (:id,:org,'Role',:user,'draft',now(),now())"), {"id": job_id, "org": organization_id, "user": user_id})
        connection.execute(text("insert into job_jd_versions(id,organization_id,job_id,version_number,content,created_by) values (:id,:org,:job,1,'{}',:user)"), {"id": version_id, "org": organization_id, "job": job_id, "user": user_id})
    for statement in ("update job_jd_versions set version_number=2 where id=:id", "delete from job_jd_versions where id=:id"):
        with pytest.raises(OperationalError):
            with pg_store.engine.begin() as connection:
                connection.execute(text(statement), {"id": version_id})
