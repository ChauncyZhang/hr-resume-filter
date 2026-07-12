import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable, Mapping

from server.app.core.logging import configure_logging
from server.app.core.probes import ReadinessProbe, check_readiness
from server.app.core.settings import Settings
from server.app.queue.service import PermanentJobError, RetryableJobError


logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        database_probe: ReadinessProbe,
        storage_probe: ReadinessProbe,
        *,
        interval_seconds: float,
        readiness_timeout_seconds: float = 5,
        queue: object | None = None,
        handlers: Mapping[str, Callable[[object], Awaitable[None]]] | None = None,
        worker_id: str = "worker",
        lease_seconds: int = 60,
        shutdown_timeout_seconds: float = 30,
        heartbeat_seconds: float = 20,
    ) -> None:
        self._database_probe = database_probe
        self._storage_probe = storage_probe
        self._interval_seconds = interval_seconds
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._shutdown = asyncio.Event()
        self._queue = queue
        self._handlers = dict(handlers or {})
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._heartbeat_seconds = heartbeat_seconds

    def request_shutdown(self) -> None:
        self._shutdown.set()

    async def run(self) -> None:
        ready = False
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(
                    check_readiness(self._database_probe, self._storage_probe),
                    timeout=self._readiness_timeout_seconds,
                )
                ready = True
            except Exception as error:
                logger.warning(
                    "worker_dependency_readiness_failed",
                    extra={"context": {"error_type": type(error).__name__}},
                )
                ready = False
            if ready and self._queue is not None:
                processing = asyncio.create_task(self._process_one())
                shutdown = asyncio.create_task(self._shutdown.wait())
                done, _ = await asyncio.wait((processing, shutdown), return_when=asyncio.FIRST_COMPLETED)
                if shutdown in done and not processing.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(processing), self._shutdown_timeout_seconds)
                    except TimeoutError:
                        processing.cancel()
                        await asyncio.gather(processing, return_exceptions=True)
                    return
                shutdown.cancel()
                await asyncio.gather(shutdown, return_exceptions=True)
                await processing
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self._interval_seconds
                )
            except TimeoutError:
                continue

    async def _process_one(self) -> None:
        job = await self._queue.claim(worker_id=self._worker_id, lease_seconds=self._lease_seconds)
        if job is None:
            return
        context = {"job_id": str(job.id), "job_type": job.type, "attempt": job.attempts, "trace_id": job.trace_id}
        handler = self._handlers.get(job.type)
        if handler is None:
            await self._queue.fail(job, self._worker_id, safe_code="unknown_job_type", retryable=False)
            logger.error("worker_job_failed", extra={"context": {**context, "safe_error_code": "unknown_job_type"}})
            return
        try:
            heartbeat = asyncio.create_task(self._heartbeat(job))
            await handler(job)
        except RetryableJobError as error:
            await self._queue.fail(job, self._worker_id, safe_code=error.safe_code, retryable=True)
            logger.error("worker_job_failed", extra={"context": {**context, "safe_error_code": error.safe_code}})
        except PermanentJobError as error:
            await self._queue.fail(job, self._worker_id, safe_code=error.safe_code, retryable=False)
            logger.error("worker_job_failed", extra={"context": {**context, "safe_error_code": error.safe_code}})
        except Exception:
            await self._queue.fail(job, self._worker_id, safe_code="handler_failed", retryable=True)
            logger.error("worker_job_failed", extra={"context": {**context, "safe_error_code": "handler_failed"}})
        else:
            await self._queue.succeed(job, self._worker_id)
        finally:
            if 'heartbeat' in locals():
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(self, job: object) -> None:
        if not hasattr(self._queue, "heartbeat"):
            return
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            await self._queue.heartbeat(job, self._worker_id, lease_seconds=self._lease_seconds)


async def _run() -> None:
    from server.app.core.storage import ObjectStorageProbe, create_storage_client
    from server.app.db.session import DatabaseProbe, create_engine
    from server.app.queue.runtime import DatabaseQueueGateway

    settings = Settings.from_environment()
    worker = Worker(
        DatabaseProbe(create_engine(settings.database_url)),
        ObjectStorageProbe(
            create_storage_client(
                settings.object_storage_endpoint,
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
                secure=settings.object_storage_secure,
                connect_timeout_seconds=settings.object_storage_connect_timeout_seconds,
                read_timeout_seconds=settings.object_storage_read_timeout_seconds,
                total_timeout_seconds=settings.object_storage_total_timeout_seconds,
            ),
            settings.object_storage_bucket,
        ),
        interval_seconds=settings.worker_poll_interval_seconds,
        readiness_timeout_seconds=settings.readiness_timeout_seconds,
        worker_id=settings.worker_id,
        lease_seconds=settings.worker_lease_seconds,
        shutdown_timeout_seconds=settings.worker_shutdown_timeout_seconds,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
        queue=DatabaseQueueGateway(settings.database_url),
        handlers={},
    )
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(event, worker.request_shutdown)
    await worker.run()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
