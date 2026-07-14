import os
import subprocess
import threading
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from server.app.core.settings import Settings
from server.app.governance.deletion_models import DeletionRequest, LegalHold
from server.app.identity.bootstrap import bootstrap_system_admin
from server.app.identity.models import Organization, User, UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.queue.models import BackgroundJob
from server.app.recruiting.models import Candidate


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured"
)
ORIGIN = "https://hr.example.test"


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
        settings=Settings(environment="test", database_url=url, cors_origins=[ORIGIN]),
        database_probe=Probe(),
        storage_probe=Probe(),
    )
    bootstrap_system_admin(
        app.state.identity_store,
        "deletion-pg",
        "Deletion PG",
        "system@deletion-pg.test",
        "System admin",
        "correct horse battery staple",
    )
    with Session(engine) as db:
        organization = db.scalar(select(Organization).where(Organization.slug == "deletion-pg"))
        users = []
        for email, role in (
            ("recruiter@deletion-pg.test", "recruiter"),
            ("recruiting-admin@deletion-pg.test", "recruiting_admin"),
        ):
            user = User(
                organization_id=organization.id,
                email=email,
                normalized_email=email,
                display_name=role,
                password_hash=PasswordService().hash("correct horse battery staple"),
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.id, role=role))
            users.append(user)
        candidate = Candidate(
            organization_id=organization.id,
            display_name="Concurrent private candidate",
            owner_id=users[0].id,
        )
        db.add(candidate)
        db.commit()
        candidate_id = candidate.id
    try:
        yield app, engine, candidate_id
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE organizations CASCADE"))
        engine.dispose()


def login(client, email):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "deletion-pg",
            "email": email,
            "password": "correct horse battery staple",
        },
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.headers["X-CSRF-Token"]}


def create_request(client, headers, candidate_id, key):
    return client.post(
        f"/api/v1/candidates/{candidate_id}/deletion-requests",
        json={"reason_code": "candidate_request"},
        headers={**headers, "Idempotency-Key": key},
    )


def test_two_request_creators_serialize_to_one_open_request(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    clients = [TestClient(app), TestClient(app)]
    headers = [login(client, "recruiter@deletion-pg.test") for client in clients]
    barrier = threading.Barrier(2)
    responses = []

    def create(index):
        barrier.wait()
        responses.append(create_request(clients[index], headers[index], candidate_id, f"request-{index}"))

    threads = [threading.Thread(target=create, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for client in clients:
        client.close()

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert next(response for response in responses if response.status_code == 409).json()["code"] == "deletion_request_open"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DeletionRequest)) == 1


def test_two_approvers_enqueue_exactly_one_job_and_stale_version_cannot_mutate(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    with TestClient(app) as creator:
        recruiter = login(creator, "recruiter@deletion-pg.test")
        created = create_request(creator, recruiter, candidate_id, "approval-request")
    request_id = created.json()["data"]["id"]
    clients = [TestClient(app), TestClient(app)]
    headers = [login(client, "system@deletion-pg.test") for client in clients]
    barrier = threading.Barrier(2)
    responses = []

    def approve(index):
        barrier.wait()
        responses.append(
            clients[index].post(
                f"/api/v1/deletion-requests/{request_id}/transitions",
                json={"target_status": "approved"},
                headers={
                    **headers[index],
                    "If-Match": '"1"',
                    "Idempotency-Key": f"approve-{index}",
                },
            )
        )

    threads = [threading.Thread(target=approve, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for client in clients:
        client.close()

    assert sorted(response.status_code for response in responses) == [200, 409]
    with Session(engine) as db:
        request = db.get(DeletionRequest, UUID(request_id))
        assert request.status == "approved" and request.version == 2
        assert db.scalar(
            select(func.count()).select_from(BackgroundJob).where(
                BackgroundJob.type == "governance.delete_candidate"
            )
        ) == 1


def test_approval_and_hold_placement_serialize_without_executable_job(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    with TestClient(app) as creator:
        recruiter = login(creator, "recruiter@deletion-pg.test")
        created = create_request(creator, recruiter, candidate_id, "race-request")
    request_id = created.json()["data"]["id"]
    approve_client, hold_client = TestClient(app), TestClient(app)
    approve_headers = login(approve_client, "system@deletion-pg.test")
    hold_headers = login(hold_client, "recruiting-admin@deletion-pg.test")
    barrier = threading.Barrier(2)
    responses = []

    def approve():
        barrier.wait()
        responses.append(
            approve_client.post(
                f"/api/v1/deletion-requests/{request_id}/transitions",
                json={"target_status": "approved"},
                headers={**approve_headers, "If-Match": '"1"', "Idempotency-Key": "race-approve"},
            )
        )

    def hold():
        barrier.wait()
        responses.append(
            hold_client.post(
                f"/api/v1/candidates/{candidate_id}/legal-holds",
                json={"reason": "Concurrent legal hold"},
                headers={**hold_headers, "Idempotency-Key": "race-hold"},
            )
        )

    threads = [threading.Thread(target=approve), threading.Thread(target=hold)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    approve_client.close()
    hold_client.close()

    assert any(response.status_code == 201 for response in responses)
    with Session(engine) as db:
        request = db.get(DeletionRequest, UUID(request_id))
        assert db.scalar(
            select(func.count()).select_from(LegalHold).where(LegalHold.released_at.is_(None))
        ) == 1
        assert request.status in {"requested", "failed"}
        active_jobs = db.scalar(
            select(func.count()).select_from(BackgroundJob).where(
                BackgroundJob.type == "governance.delete_candidate",
                BackgroundJob.status.in_(("queued", "running")),
            )
        )
        assert active_jobs == 0


def test_failed_retry_refreshes_manifest_and_uses_new_version_once(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    with TestClient(app) as client:
        recruiter = login(client, "recruiter@deletion-pg.test")
        created = create_request(client, recruiter, candidate_id, "retry-request")
        request_id = created.json()["data"]["id"]
        with Session(engine) as db:
            request = db.get(DeletionRequest, UUID(request_id))
            request.status = "failed"
            request.safe_error_code = "worker_failed"
            request.version = 2
            candidate = db.get(Candidate, candidate_id)
            candidate.version += 1
            db.commit()
        system = login(client, "system@deletion-pg.test")
        retried = client.post(
            f"/api/v1/deletion-requests/{request_id}/transitions",
            json={"target_status": "approved"},
            headers={**system, "If-Match": '"2"', "Idempotency-Key": "retry-approve"},
        )
        replay = client.post(
            f"/api/v1/deletion-requests/{request_id}/transitions",
            json={"target_status": "approved"},
            headers={**system, "If-Match": '"2"', "Idempotency-Key": "retry-approve"},
        )
    assert retried.status_code == replay.status_code == 200
    assert retried.json() == replay.json()
    assert retried.json()["data"]["version"] == 3
    with Session(engine) as db:
        assert db.scalar(
            select(func.count()).select_from(BackgroundJob).where(
                BackgroundJob.dedupe_key == f"candidate-delete:{request_id}:3"
            )
        ) == 1
