import os
import subprocess
import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from server.app.queue.models import BackgroundJob, JobAttempt, OutboxEvent
from server.app.queue.repository import LeaseRejected, QueueRepository


pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")


@pytest.fixture
def queue_db():
    async_url = os.environ["POSTGRES_SMOKE_URL"]
    env = {**os.environ, "DATABASE_URL": async_url}
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env=env)
    engine = create_engine(async_url.replace("+asyncpg", "+psycopg"))
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE outbox_events, job_attempts, background_jobs, organizations CASCADE"))
    yield engine
    engine.dispose()


def organization(session: Session, slug: str) -> uuid.UUID:
    organization_id = uuid.uuid4()
    session.execute(text("INSERT INTO organizations (id, slug, name, status, created_at, updated_at) VALUES (:id, :slug, :slug, 'active', now(), now())"), {"id": organization_id, "slug": slug})
    return organization_id


def test_enqueue_and_outbox_are_transactional_and_dedupe_is_terminal_aware(queue_db) -> None:
    with Session(queue_db) as session:
        org = organization(session, "atomic")
        repo = QueueRepository(session)
        first = repo.enqueue(org, "export", {"export_id": str(uuid.uuid4())}, dedupe_key="same")
        assert repo.enqueue(org, "export", {"export_id": str(uuid.uuid4())}, dedupe_key="same").id == first.id
        repo.append_outbox(org, "audit.created", "candidate", uuid.uuid4(), {"candidate_id": str(uuid.uuid4())})
        session.rollback()
    with Session(queue_db) as session:
        assert session.scalar(select(BackgroundJob)) is None
        assert session.scalar(select(OutboxEvent)) is None
        org = organization(session, "terminal")
        repo = QueueRepository(session)
        first = repo.enqueue(org, "export", {}, dedupe_key="same")
        session.commit()
        claimed = repo.claim(org, "w1", lease_seconds=30)
        repo.succeed(org, claimed.id, "w1")
        session.commit()
        assert repo.enqueue(org, "export", {}, dedupe_key="same").id != first.id


def test_claim_is_exclusive_and_ordered(queue_db) -> None:
    with Session(queue_db) as session:
        org = organization(session, "claim")
        repo = QueueRepository(session)
        low = repo.enqueue(org, "work", {}, priority=1)
        high = repo.enqueue(org, "work", {}, priority=9)
        future = repo.enqueue(org, "work", {}, priority=99, run_after=repo.database_now() + timedelta(hours=1))
        session.commit()
        low_id, high_id, future_id = low.id, high.id, future.id
    barrier = threading.Barrier(2)
    claimed: list[uuid.UUID | None] = []
    def take(worker: str) -> None:
        with Session(queue_db) as session:
            barrier.wait()
            item = QueueRepository(session).claim(org, worker, lease_seconds=30)
            claimed.append(item.id if item else None)
            session.commit()
    threads = [threading.Thread(target=take, args=(f"w{i}",)) for i in range(2)]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert set(claimed) == {high_id, low_id}
    assert future_id not in claimed


def test_owner_checks_reclaim_retry_cancel_and_tenant_isolation(queue_db) -> None:
    with Session(queue_db) as session:
        org = organization(session, "owner")
        other = organization(session, "other")
        repo = QueueRepository(session, jitter=lambda _: 0)
        job = repo.enqueue(org, "work", {}, max_attempts=2)
        session.commit()
        claimed = repo.claim(org, "old", lease_seconds=30)
        with pytest.raises(LeaseRejected): repo.heartbeat(org, job.id, "wrong", lease_seconds=30)
        with pytest.raises(LeaseRejected): repo.succeed(other, job.id, "old")
        session.execute(text("UPDATE background_jobs SET lease_expires_at = now() - interval '1 second' WHERE id=:id"), {"id": job.id})
        session.commit()
        reclaimed = repo.claim(org, "new", lease_seconds=30)
        assert reclaimed.id == job.id and reclaimed.attempts == 2
        with pytest.raises(LeaseRejected): repo.succeed(org, job.id, "old")
        repo.fail(org, job.id, "new", safe_code="temporary", retryable=True)
        session.commit()
        stored = session.get(BackgroundJob, job.id)
        assert stored.status == "dead_letter"
        attempts = session.scalars(select(JobAttempt).where(JobAttempt.job_id == job.id).order_by(JobAttempt.attempt_no)).all()
        assert [attempt.result for attempt in attempts] == ["abandoned", "failed"]
        cancelled = repo.enqueue(org, "cancel", {})
        assert repo.cancel(org, cancelled.id)
        assert repo.cancel(org, cancelled.id)
        session.commit()
        assert repo.claim(org, "new", lease_seconds=30) is None


def test_outbox_retries_and_publishes_once_and_attempt_history_is_immutable(queue_db) -> None:
    with Session(queue_db) as session:
        org = organization(session, "outbox")
        repo = QueueRepository(session, jitter=lambda _: 0)
        event = repo.append_outbox(org, "audit.created", "candidate", uuid.uuid4(), {"candidate_id": str(uuid.uuid4())}, max_attempts=2)
        job = repo.enqueue(org, "work", {})
        session.commit()
        claimed = repo.claim_outbox(org, "d1", lease_seconds=30)
        repo.fail_outbox(org, claimed.id, "d1", safe_code="temporary", retryable=True)
        session.flush()
        session.execute(text("UPDATE outbox_events SET available_at=now() WHERE id=:id"), {"id": event.id})
        claimed = repo.claim_outbox(org, "d2", lease_seconds=30)
        repo.publish_outbox(org, claimed.id, "d2")
        running = repo.claim(org, "w", lease_seconds=30)
        repo.succeed(org, running.id, "w")
        session.commit()
        with pytest.raises(LeaseRejected): repo.publish_outbox(org, event.id, "d2")
        with pytest.raises(Exception):
            session.execute(text("UPDATE job_attempts SET result='changed' WHERE job_id=:id"), {"id": job.id})
