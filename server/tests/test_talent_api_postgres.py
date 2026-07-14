import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from server.app.identity.models import Job, JobCollaborator
from server.app.recruiting.models import Application
from server.tests.test_interview_api import seed_application
from server.tests.test_interview_api_postgres import postgres_app
from server.tests.test_recruiting_api import login
from server.tests.test_talent_api import create_pool_and_membership


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured"
)


def test_postgres_concurrent_reactivations_create_only_one_active_application() -> None:
    app = postgres_app()
    seed = seed_application(app)
    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        source.stage = "rejected"
        source.version += 1
        target = Job(
            organization_id=source.organization_id,
            title="Concurrent RAG Engineer",
            owner_id=seed["admin_id"],
            status="open",
        )
        database.add(target)
        database.flush()
        database.add(
            JobCollaborator(
                organization_id=source.organization_id,
                job_id=target.id,
                user_id=seed["admin_id"],
                access_role="job_owner",
            )
        )
        database.commit()
        target_id = target.id

    with TestClient(app) as client:
        _, _, membership = create_pool_and_membership(client, seed)
        membership_id = membership.json()["data"]["id"]

    def reactivate(key):
        with TestClient(app) as client:
            return client.post(
                f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
                json={"job_id": str(target_id)},
                headers={**login(client, "interview-admin@example.test"), "Idempotency-Key": key},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(reactivate, ("concurrent-reactivate-a", "concurrent-reactivate-b")))

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["code"] == "active_application_exists"

    with app.state.identity_store.sync_session() as database:
        active = database.query(Application).filter(
            Application.organization_id == source.organization_id,
            Application.candidate_id == seed["candidate_id"],
            Application.job_id == target_id,
            Application.stage.not_in(("hired", "rejected", "withdrawn")),
        ).all()
        assert len(active) == 1
        assert active[0].source_application_id == seed["application_id"]
