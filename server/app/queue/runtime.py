import asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from server.app.identity.models import Organization
from server.app.queue.repository import QueueRepository


class DatabaseQueueGateway:
    """Short-transaction async adapter used by the single-job worker loop."""
    def __init__(self, database_url: str) -> None:
        sync_url = database_url.replace("+asyncpg", "+psycopg")
        self._sessions = sessionmaker(create_engine(sync_url, pool_pre_ping=True), expire_on_commit=False)

    async def claim(self, *, worker_id: str, lease_seconds: int):
        return await asyncio.to_thread(self._claim, worker_id, lease_seconds)

    def _claim(self, worker_id: str, lease_seconds: int):
        with self._sessions.begin() as session:
            organization_ids = session.scalars(select(Organization.id).order_by(Organization.id)).all()
            for organization_id in organization_ids:
                if job := QueueRepository(session).claim(organization_id, worker_id, lease_seconds=lease_seconds):
                    session.expunge(job)
                    return job
        return None

    async def succeed(self, job, worker_id: str) -> None:
        await asyncio.to_thread(self._complete, job, worker_id, None, False)

    async def fail(self, job, worker_id: str, *, safe_code: str, retryable: bool) -> None:
        await asyncio.to_thread(self._complete, job, worker_id, safe_code, retryable)

    def _complete(self, job, worker_id: str, safe_code: str | None, retryable: bool) -> None:
        with self._sessions.begin() as session:
            repository = QueueRepository(session)
            if safe_code is None: repository.succeed(job.organization_id, job.id, worker_id)
            else: repository.fail(job.organization_id, job.id, worker_id, safe_code=safe_code, retryable=retryable)

    async def heartbeat(self, job, worker_id: str, *, lease_seconds: int) -> None:
        def extend() -> None:
            with self._sessions.begin() as session: QueueRepository(session).heartbeat(job.organization_id, job.id, worker_id, lease_seconds=lease_seconds)
        await asyncio.to_thread(extend)
