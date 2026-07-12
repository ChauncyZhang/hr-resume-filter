import asyncio
import logging
import signal

from server.app.core.probes import ReadinessProbe
from server.app.core.logging import configure_logging
from server.app.core.settings import Settings


logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        database_probe: ReadinessProbe,
        storage_probe: ReadinessProbe,
        *,
        interval_seconds: float,
        readiness_timeout_seconds: float = 5,
    ) -> None:
        self._database_probe = database_probe
        self._storage_probe = storage_probe
        self._interval_seconds = interval_seconds
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._shutdown = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown.set()

    async def run(self) -> None:
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self._database_probe.check(), self._storage_probe.check()
                    ),
                    timeout=self._readiness_timeout_seconds,
                )
            except Exception as error:
                logger.warning(
                    "worker_dependency_readiness_failed",
                    extra={"context": {"error_type": type(error).__name__}},
                )
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(), timeout=self._interval_seconds
                )
            except TimeoutError:
                continue


async def _run() -> None:
    from server.app.core.storage import ObjectStorageProbe, create_storage_client
    from server.app.db.session import DatabaseProbe, create_engine

    settings = Settings.from_environment()
    worker = Worker(
        DatabaseProbe(create_engine(settings.database_url)),
        ObjectStorageProbe(
            create_storage_client(
                settings.object_storage_endpoint,
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
                secure=settings.object_storage_secure,
            ),
            settings.object_storage_bucket,
        ),
        interval_seconds=settings.worker_check_interval_seconds,
        readiness_timeout_seconds=settings.readiness_timeout_seconds,
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
