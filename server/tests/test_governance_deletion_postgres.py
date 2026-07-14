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
BARRIER_TIMEOUT_SECONDS = 10
THREAD_JOIN_TIMEOUT_SECONDS = 30


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


def run_concurrently(*workers) -> None:
    barrier = threading.Barrier(len(workers))
    worker_errors = []
    error_lock = threading.Lock()

    def guarded(worker) -> None:
        try:
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            worker()
        except BaseException as error:
            with error_lock:
                worker_errors.append(error)

    threads = [
        threading.Thread(target=guarded, args=(worker,), daemon=True)
        for worker in workers
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)

    alive = [thread.name for thread in threads if thread.is_alive()]
    if alive:
        barrier.abort()
    assert not alive, f"concurrent workers remained alive: {alive}"
    assert not worker_errors, f"concurrent worker failures: {worker_errors!r}"


def test_two_request_creators_serialize_to_one_open_request(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    clients = [TestClient(app), TestClient(app)]
    headers = [login(client, "recruiter@deletion-pg.test") for client in clients]
    responses = []

    def create(index):
        responses.append(create_request(clients[index], headers[index], candidate_id, f"request-{index}"))

    run_concurrently(*(lambda index=index: create(index) for index in range(2)))
    for client in clients:
        client.close()

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert next(response for response in responses if response.status_code == 409).json()["code"] == "deletion_request_open"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DeletionRequest)) == 1


def test_same_key_different_candidates_never_replays_cross_candidate(postgres_app) -> None:
    app, engine, first_id = postgres_app
    with Session(engine) as db:
        owner = db.scalar(select(User).where(User.email == "recruiter@deletion-pg.test"))
        second = Candidate(organization_id=owner.organization_id, display_name="Second", owner_id=owner.id)
        db.add(second); db.commit(); second_id = second.id
    clients = [TestClient(app), TestClient(app)]
    headers = [login(client, "recruiter@deletion-pg.test") for client in clients]
    responses = []

    def create(index, candidate_id):
        responses.append(create_request(clients[index], headers[index], candidate_id, "same-resource-key"))

    run_concurrently(
        lambda: create(0, first_id),
        lambda: create(1, second_id),
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert next(r for r in responses if r.status_code == 409).json()["code"] == "idempotency_conflict"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DeletionRequest)) == 1
    for client in clients: client.close()


def test_two_approvers_enqueue_exactly_one_job_and_stale_version_cannot_mutate(postgres_app) -> None:
    app, engine, candidate_id = postgres_app
    with TestClient(app) as creator:
        recruiter = login(creator, "recruiter@deletion-pg.test")
        created = create_request(creator, recruiter, candidate_id, "approval-request")
    request_id = created.json()["data"]["id"]
    clients = [TestClient(app), TestClient(app)]
    headers = [login(client, "system@deletion-pg.test") for client in clients]
    responses = []

    def approve(index):
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

    run_concurrently(*(lambda index=index: approve(index) for index in range(2)))
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
    responses = {}

    def approve():
        responses["approval"] = approve_client.post(
            f"/api/v1/deletion-requests/{request_id}/transitions",
            json={"target_status": "approved"},
            headers={**approve_headers, "If-Match": '"1"', "Idempotency-Key": "race-approve"},
        )

    def hold():
        responses["hold"] = hold_client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Concurrent legal hold"},
            headers={**hold_headers, "Idempotency-Key": "race-hold"},
        )

    run_concurrently(approve, hold)
    approve_client.close()
    hold_client.close()

    assert set(responses) == {"approval", "hold"}
    approval_response = responses["approval"]
    hold_response = responses["hold"]
    assert hold_response.status_code == 201
    assert hold_response.headers["ETag"] == '"1"'
    assert hold_response.json()["data"]["status"] == "active"
    assert hold_response.json()["data"]["version"] == 1
    assert hold_response.json()["data"]["reason"] == "Concurrent legal hold"

    with Session(engine) as db:
        request = db.get(DeletionRequest, UUID(request_id))
        active_holds = list(
            db.scalars(select(LegalHold).where(LegalHold.released_at.is_(None)))
        )
        jobs = list(
            db.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.type == "governance.delete_candidate"
                )
            )
        )
        assert len(active_holds) == 1
        assert not any(job.status in {"queued", "running"} for job in jobs)

        if approval_response.status_code == 409:
            assert approval_response.json()["code"] == "legal_hold_active"
            assert request.status == "requested"
            assert request.version == 1
            assert request.safe_error_code is None
            assert jobs == []
        elif approval_response.status_code == 200:
            assert approval_response.json()["data"]["status"] == "approved"
            assert approval_response.json()["data"]["version"] == 2
            assert request.status == "failed"
            assert request.version == 3
            assert request.safe_error_code == "legal_hold_active"
            assert len(jobs) == 1
            assert jobs[0].dedupe_key == f"candidate-delete:{request_id}:2"
            assert jobs[0].status == "cancelled"
        else:
            pytest.fail(
                "approve-vs-hold produced an illegal response serialization: "
                f"approval={approval_response.status_code} "
                f"body={approval_response.json()!r}"
            )


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
