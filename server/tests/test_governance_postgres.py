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
from server.app.governance import service as governance_service
from server.app.governance.models import RetentionPolicy
from server.app.governance.service import aware, candidate_due_dates
from server.app.identity.models import AuditLog, Job, Organization, User, UserRole
from server.app.identity.bootstrap import bootstrap_system_admin
from server.app.interviews.models import Interview, InterviewFeedback, InterviewParticipant
from server.app.main import create_app
from server.app.recruiting.models import Application, Candidate, FileObject, IdempotencyRecord, Resume
from server.app.recruiting.service import create_application_record, persisted_idempotent
from server.app.talent.models import TalentPool


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


def _seed_concurrent_retention_fact_writers(engine):
    old = datetime.now(timezone.utc) - timedelta(days=30)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == "governance-pg@test"))
        db.add_all([UserRole(user_id=user.id, role="recruiting_admin"), UserRole(user_id=user.id, role="interviewer")])
        candidate = Candidate(
            organization_id=user.organization_id,
            display_name="Fact writer candidate",
            owner_id=user.id,
            created_at=old,
            updated_at=old,
            retention_due_at=old + timedelta(days=365),
        )
        job = Job(organization_id=user.organization_id, title="Fact writer job", owner_id=user.id, status="open")
        file = FileObject(
            organization_id=user.organization_id,
            storage_key=f"private/{uuid4()}",
            original_filename="fact.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="c" * 64,
            uploaded_by=user.id,
        )
        db.add_all([candidate, job, file])
        db.flush()
        resume = Resume(organization_id=user.organization_id, candidate_id=candidate.id, file_object_id=file.id, version_number=1)
        db.add(resume)
        db.flush()
        application = Application(
            organization_id=user.organization_id,
            candidate_id=candidate.id,
            job_id=job.id,
            resume_id=resume.id,
            owner_id=user.id,
            stage="hired",
            created_at=old,
            updated_at=old,
        )
        pool = TalentPool(
            organization_id=user.organization_id,
            name="Fact pool",
            purpose="Concurrent retention facts",
            owner_id=user.id,
            suitable_roles=["Engineer"],
        )
        db.add_all([application, pool])
        db.flush()
        interview = Interview(
            organization_id=user.organization_id,
            application_id=application.id,
            round_name="Final",
            method="video",
            timezone="UTC",
            starts_at=old,
            ends_at=old + timedelta(hours=1),
            meeting_url="https://meet.example.test/fact",
            status="feedback_completed",
            owner_id=user.id,
            created_by=user.id,
            created_at=old,
            updated_at=old,
        )
        db.add(interview)
        db.flush()
        participant = InterviewParticipant(
            organization_id=user.organization_id,
            interview_id=interview.id,
            user_id=user.id,
            role="interviewer",
            required_feedback=True,
            task_status="completed",
        )
        db.add(participant)
        db.flush()
        feedback = InterviewFeedback(
            organization_id=user.organization_id,
            interview_id=interview.id,
            author_id=user.id,
            status="submitted",
            ratings={"technical": 4, "communication": 4, "problem_solving": 4},
            strengths="Strong",
            risks="None",
            conclusion="recommend",
            notes="Original",
            version=1,
            submitted_at=old,
            created_at=old,
            updated_at=old,
        )
        db.add(feedback)
        db.commit()
        return {
            "organization_id": user.organization_id,
            "user_id": user.id,
            "candidate_id": candidate.id,
            "application_id": application.id,
            "pool_id": pool.id,
            "feedback_id": feedback.id,
        }


@pytest.mark.parametrize("writer_kind", ["talent", "feedback", "event"])
def test_retention_patch_serializes_with_every_retention_fact_writer(
    postgres_app, monkeypatch, writer_kind
) -> None:
    app, engine = postgres_app
    ids = _seed_concurrent_retention_fact_writers(engine)
    snapshot_ready = threading.Event()
    release_patch = threading.Event()
    writer_done = threading.Event()
    responses = {}
    original = governance_service.affected_candidate_ids

    def paused_snapshot(*args, **kwargs):
        result = original(*args, **kwargs)
        snapshot_ready.set()
        assert release_patch.wait(10)
        return result

    monkeypatch.setattr(governance_service, "affected_candidate_ids", paused_snapshot)

    def patch_policy():
        with TestClient(app) as client:
            headers = _login(client)
            responses["patch"] = client.patch(
                "/api/v1/settings/retention-policy",
                json={"terminal_days": 400, "talent_pool_days": 730, "backup_window_days": 90},
                headers={**headers, "If-Match": '"1"', "Idempotency-Key": f"fact-{writer_kind}"},
            )

    def write_fact():
        with TestClient(app) as client:
            headers = _login(client)
            if writer_kind == "talent":
                responses["writer"] = client.post(
                    f"/api/v1/talent-pools/{ids['pool_id']}/memberships",
                    json={
                        "candidate_id": str(ids["candidate_id"]),
                        "owner_id": str(ids["user_id"]),
                        "suitable_roles": ["Engineer"],
                        "tags": [],
                        "reason": "Concurrent fact",
                        "retention_until": (datetime.now(timezone.utc) + timedelta(days=900)).isoformat(),
                    },
                    headers={**headers, "Idempotency-Key": "fact-talent-writer"},
                )
            elif writer_kind == "feedback":
                responses["writer"] = client.post(
                    f"/api/v1/interview-feedback/{ids['feedback_id']}/amendments",
                    json={
                        "ratings": {
                            "professional_ability": 4,
                            "problem_solving": 4,
                            "communication": 4,
                            "role_fit": 4,
                        },
                        "strengths": "Stronger",
                        "risks": "Low",
                        "conclusion": "strong_recommend",
                        "notes": "Amended",
                        "reason": "New evidence",
                    },
                    headers={**headers, "If-Match": '"1"'},
                )
            else:
                responses["writer"] = client.post(
                    f"/api/v1/candidates/{ids['candidate_id']}/notes",
                    json={"application_id": str(ids["application_id"]), "body": "Concurrent event"},
                    headers=headers,
                )
        writer_done.set()

    patch_thread = threading.Thread(target=patch_policy)
    patch_thread.start()
    assert snapshot_ready.wait(10)
    writer_thread = threading.Thread(target=write_fact)
    writer_thread.start()
    writer_was_serialized = not writer_done.wait(0.75)
    release_patch.set()
    patch_thread.join(10)
    writer_thread.join(10)

    assert not patch_thread.is_alive() and not writer_thread.is_alive()
    assert writer_was_serialized
    assert responses["patch"].status_code == 200
    assert responses["writer"].status_code in {200, 201}
    with Session(engine) as db:
        candidate = db.get(Candidate, ids["candidate_id"])
        expected = candidate_due_dates(db, ids["organization_id"], 400)[ids["candidate_id"]]
        assert aware(candidate.retention_due_at) == aware(expected)
