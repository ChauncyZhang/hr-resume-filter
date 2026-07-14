import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from server.app.core.settings import Settings
from server.app.governance.models import RetentionPolicy
from server.app.identity.models import AuditLog, Job, Organization, User
from server.app.identity.bootstrap import bootstrap_system_admin
from server.app.main import create_app
from server.app.recruiting.models import Candidate, FileObject, IdempotencyRecord, Resume
from server.app.recruiting.service import create_application_record, persisted_idempotent


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured"
)


class Probe:
    async def check(self) -> None:
        pass


@pytest.fixture
def postgres_app():
    url = os.environ["POSTGRES_SMOKE_URL"]
    subprocess.run(
        ["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": url},
    )
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE organizations CASCADE"))
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=url,
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
    )
    bootstrap_system_admin(
        app.state.identity_store,
        "governance-pg",
        "Governance PG",
        "governance-pg@test",
        "Governance admin",
        "correct horse battery staple",
    )
    yield app, engine
    engine.dispose()


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "governance-pg",
            "email": "governance-pg@test",
            "password": "correct horse battery staple",
        },
        headers={"Origin": "https://hr.example.test"},
    )
    assert response.status_code == 200
    return {
        "Origin": "https://hr.example.test",
        "X-CSRF-Token": response.headers["X-CSRF-Token"],
    }


def test_concurrent_patch_commits_one_version_and_one_audit(postgres_app) -> None:
    app, engine = postgres_app
    clients = [TestClient(app), TestClient(app)]
    headers = [_login(client) for client in clients]
    barrier = threading.Barrier(2)
    results = []

    def patch(index):
        barrier.wait()
        results.append(
            clients[index].patch(
                "/api/v1/settings/retention-policy",
                json={
                    "terminal_days": 400,
                    "talent_pool_days": 730,
                    "backup_window_days": 90,
                },
                headers={
                    **headers[index],
                    "If-Match": '"1"',
                    "Idempotency-Key": f"concurrent-{index}",
                },
            )
        )

    threads = [threading.Thread(target=patch, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for client in clients:
        client.close()

    assert sorted(response.status_code for response in results) == [200, 409]
    assert next(response for response in results if response.status_code == 409).json()["code"] == "resource_version_conflict"
    with Session(engine) as db:
        assert db.scalar(select(RetentionPolicy.version)) == 2
        assert db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.event_type == "retention_policy.updated"
            )
        ) == 1


def _seed_application_facts(engine):
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "governance-pg@test"))
        candidate = Candidate(
            organization_id=user.organization_id,
            display_name="Concurrent candidate",
            owner_id=user.id,
            retention_due_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        job = Job(
            organization_id=user.organization_id,
            title="Concurrent job",
            owner_id=user.id,
            status="open",
        )
        file = FileObject(
            organization_id=user.organization_id,
            storage_key=f"private/{uuid4()}",
            original_filename="candidate.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="b" * 64,
            uploaded_by=user.id,
        )
        db.add_all([candidate, job, file])
        db.flush()
        resume = Resume(
            organization_id=user.organization_id,
            candidate_id=candidate.id,
            file_object_id=file.id,
            version_number=1,
        )
        db.add(resume)
        db.commit()
        return user.id, user.organization_id, candidate.id, job.id, resume.id


def test_retention_patch_serializes_with_concurrent_active_application(postgres_app) -> None:
    app, engine = postgres_app
    user_id, organization_id, candidate_id, job_id, resume_id = _seed_application_facts(engine)
    application_locked = threading.Event()
    allow_application_commit = threading.Event()
    patch_started = threading.Event()
    results = {}

    def create_application():
        with Session(engine) as db:
            create_application_record(
                db,
                organization_id=organization_id,
                candidate_id=candidate_id,
                job_id=job_id,
                resume_id=resume_id,
                owner_id=user_id,
            )
            application_locked.set()
            assert allow_application_commit.wait(10)
            db.commit()

    with TestClient(app) as client:
        headers = _login(client)

        def patch_policy():
            patch_started.set()
            results["response"] = client.patch(
                "/api/v1/settings/retention-policy",
                json={
                    "terminal_days": 400,
                    "talent_pool_days": 730,
                    "backup_window_days": 90,
                },
                headers={
                    **headers,
                    "If-Match": '"1"',
                    "Idempotency-Key": "application-barrier",
                },
            )

        application_thread = threading.Thread(target=create_application)
        application_thread.start()
        assert application_locked.wait(10)
        patch_thread = threading.Thread(target=patch_policy)
        patch_thread.start()
        assert patch_started.wait(10)
        time.sleep(0.5)
        allow_application_commit.set()
        application_thread.join(10)
        patch_thread.join(10)

    assert not application_thread.is_alive() and not patch_thread.is_alive()
    assert results["response"].status_code == 200
    with Session(engine) as db:
        assert db.get(Candidate, candidate_id).retention_due_at is None


def test_expired_idempotency_key_concurrency_executes_replacement_once(postgres_app) -> None:
    _, engine = postgres_app
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "governance-pg@test"))
        db.add(
            IdempotencyRecord(
                organization_id=user.organization_id,
                user_id=user.id,
                operation="retention_policy.update",
                idempotency_key="expired-concurrent",
                request_hash="0" * 64,
                status_code=200,
                response_json={"stale": True},
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        db.commit()
        organization_id, user_id = user.organization_id, user.id

    barrier = threading.Barrier(2)
    action_count = 0
    action_lock = threading.Lock()
    results = []

    def execute():
        nonlocal action_count
        with Session(engine) as db:
            barrier.wait()

            def action():
                nonlocal action_count
                with action_lock:
                    action_count += 1
                return 200, {"fresh": True}

            results.append(
                persisted_idempotent(
                    db,
                    organization_id,
                    user_id,
                    "retention_policy.update",
                    "expired-concurrent",
                    {"version": 2},
                    action,
                )
            )
            db.commit()

    threads = [threading.Thread(target=execute) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert all(not thread.is_alive() for thread in threads)
    assert action_count == 1
    assert results == [(200, {"fresh": True}), (200, {"fresh": True})]
    with Session(engine) as db:
        records = db.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == "retention_policy.update",
                IdempotencyRecord.idempotency_key == "expired-concurrent",
            )
        ).all()
        assert len(records) == 1 and records[0].response_json == {"fresh": True}
