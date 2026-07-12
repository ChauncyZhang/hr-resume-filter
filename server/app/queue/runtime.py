import asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from server.app.identity.models import Organization
from server.app.queue.repository import QueueRepository
from server.app.queue.payloads import DEFAULT_PAYLOAD_POLICIES, PayloadPolicyRegistry


class DatabaseQueueGateway:
    """Short-transaction async adapter used by the single-job worker loop."""
    def __init__(self, database_url: str, policies: PayloadPolicyRegistry = DEFAULT_PAYLOAD_POLICIES) -> None:
        sync_url = database_url.replace("+asyncpg", "+psycopg")
        self._sessions = sessionmaker(create_engine(sync_url, pool_pre_ping=True), expire_on_commit=False)
        self._policies = policies

    async def claim_job(self, *, worker_id: str, lease_seconds: int):
        return await asyncio.to_thread(self._claim, "job", worker_id, lease_seconds)

    async def claim_outbox(self, *, worker_id: str, lease_seconds: int):
        return await asyncio.to_thread(self._claim, "outbox", worker_id, lease_seconds)

    def _claim(self, kind: str, worker_id: str, lease_seconds: int):
        with self._sessions.begin() as session:
            organization_ids = session.scalars(select(Organization.id).order_by(Organization.id)).all()
            for organization_id in organization_ids:
                repository = QueueRepository(session, policies=self._policies)
                item = repository.claim(organization_id, worker_id, lease_seconds=lease_seconds) if kind == "job" else repository.claim_outbox(organization_id, worker_id, lease_seconds=lease_seconds)
                if item:
                    session.expunge(item); return item
        return None

    async def succeed(self, job, worker_id: str) -> None:
        await asyncio.to_thread(self._complete, job, worker_id, None, False)

    async def fail(self, job, worker_id: str, *, safe_code: str, retryable: bool) -> None:
        await asyncio.to_thread(self._complete, job, worker_id, safe_code, retryable)

    def _complete(self, job, worker_id: str, safe_code: str | None, retryable: bool) -> None:
        with self._sessions.begin() as session:
            repository = QueueRepository(session, policies=self._policies)
            if safe_code is None: repository.succeed(job.organization_id, job.id, worker_id)
            else: repository.fail(job.organization_id, job.id, worker_id, safe_code=safe_code, retryable=retryable)

    async def heartbeat(self, job, worker_id: str, *, lease_seconds: int) -> None:
        def extend() -> None:
            with self._sessions.begin() as session: QueueRepository(session, policies=self._policies).heartbeat(job.organization_id, job.id, worker_id, lease_seconds=lease_seconds)
        await asyncio.to_thread(extend)

    async def publish_outbox(self, event, worker_id: str) -> None:
        await asyncio.to_thread(self._outbox_complete, event, worker_id, None, False)

    async def fail_outbox(self, event, worker_id: str, *, safe_code: str, retryable: bool) -> None:
        await asyncio.to_thread(self._outbox_complete, event, worker_id, safe_code, retryable)

    def _outbox_complete(self, event, worker_id: str, safe_code: str | None, retryable: bool) -> None:
        with self._sessions.begin() as session:
            repository = QueueRepository(session, policies=self._policies)
            if safe_code is None: repository.publish_outbox(event.organization_id, event.id, worker_id)
            else: repository.fail_outbox(event.organization_id, event.id, worker_id, safe_code=safe_code, retryable=retryable)

    async def heartbeat_outbox(self, event, worker_id: str, *, lease_seconds: int) -> None:
        def extend() -> None:
            with self._sessions.begin() as session: QueueRepository(session, policies=self._policies).heartbeat_outbox(event.organization_id, event.id, worker_id, lease_seconds=lease_seconds)
        await asyncio.to_thread(extend)
