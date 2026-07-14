import os
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from server.app.core.settings import Settings
from server.app.governance.models import RetentionPolicy
from server.app.identity.models import AuditLog
from server.app.identity.bootstrap import bootstrap_system_admin
from server.app.main import create_app


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
