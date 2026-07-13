import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable, Mapping

from server.app.core.logging import configure_logging
from server.app.core.probes import ReadinessProbe, check_readiness
from server.app.core.settings import Settings
from server.app.queue.service import PermanentJobError, RetryableJobError, normalize_safe_code
from server.app.queue.payloads import IDENTIFIER_PATTERN, TYPE_PATTERN

logger = logging.getLogger(__name__)

def build_screening_handlers(settings,storage_client,bucket):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from server.app.screening.pipeline import ScreeningPipeline
    from server.app.screening.scanner import ClamAvScanner
    from server.app.screening.storage import PipelineStorage
    from server.app.screening.llm_pipeline import LlmScreeningPipeline
    from server.app.llm.gateway import OpenAiCompatibleGateway
    from server.app.llm.policy import ProviderAllowlist
    from server.app.llm.security import ApiKeyCipher
    sessions=sessionmaker(create_engine(settings.database_url.replace("+asyncpg","+psycopg")),expire_on_commit=False)
    scanner=ClamAvScanner(settings.clamav_host,settings.clamav_port,connect_timeout=settings.clamav_connect_timeout_seconds,read_timeout=settings.clamav_read_timeout_seconds,total_timeout=settings.clamav_total_timeout_seconds)
    pipeline=ScreeningPipeline(sessions,PipelineStorage(storage_client,bucket),scanner,settings)
    llm_key=settings.llm_config_encryption_key.get_secret_value()
    if llm_key=="change-me": llm_key="QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8="
    allowlist=ProviderAllowlist(settings.llm_provider_allowlist,allow_http=settings.environment!="production")
    llm_pipeline=LlmScreeningPipeline(sessions,OpenAiCompatibleGateway(allowlist),ApiKeyCipher(llm_key.encode()))
    return {"screening.parse_item":pipeline.parse_item,"screening.score_item":pipeline.score_item,"screening.llm_score_item":llm_pipeline.evaluate_item}


class Worker:
    def __init__(self, database_probe: ReadinessProbe, storage_probe: ReadinessProbe, *, interval_seconds: float,
                 readiness_timeout_seconds: float = 5, queue: object | None = None,
                 handlers: Mapping[str, Callable[[object], Awaitable[None]]] | None = None,
                 outbox_handlers: Mapping[str, Callable[[object, object], Awaitable[None]]] | None = None,
                 worker_id: str = "worker", lease_seconds: int = 60, shutdown_timeout_seconds: float = 30,
                 cancel_timeout_seconds: float = 5, heartbeat_seconds: float = 20,
                 hard_stop: Callable[[], None] | None = None) -> None:
        self._database_probe = database_probe; self._storage_probe = storage_probe
        self._interval_seconds = interval_seconds; self._readiness_timeout_seconds = readiness_timeout_seconds
        self._queue = queue; self._handlers = dict(handlers or {}); self._outbox_handlers = dict(outbox_handlers or {})
        self._worker_id = worker_id; self._lease_seconds = lease_seconds; self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._cancel_timeout_seconds = cancel_timeout_seconds; self._heartbeat_seconds = heartbeat_seconds
        self._hard_stop = hard_stop or (lambda: os._exit(1)); self._shutdown = asyncio.Event(); self._next_kind = "job"
        self._active_handler: asyncio.Task[None] | None = None

    def request_shutdown(self) -> None: self._shutdown.set()

    async def run(self) -> None:
        while not self._shutdown.is_set():
            if not await self._ready():
                await self._pause(); continue
            processing = asyncio.create_task(self._poll_once())
            stopping = asyncio.create_task(self._shutdown.wait())
            done, _ = await asyncio.wait((processing, stopping), return_when=asyncio.FIRST_COMPLETED)
            if stopping in done and not processing.done():
                try: await asyncio.wait_for(asyncio.shield(processing), self._shutdown_timeout_seconds)
                except TimeoutError:
                    if self._active_handler is not None:
                        self._active_handler.cancel()
                        try: await asyncio.wait_for(asyncio.shield(self._active_handler), self._cancel_timeout_seconds)
                        except TimeoutError: self._hard_stop()
                        except asyncio.CancelledError: pass
                    processing.cancel(); await asyncio.gather(processing, return_exceptions=True)
                return
            stopping.cancel(); await asyncio.gather(stopping, return_exceptions=True)
            await asyncio.gather(processing, return_exceptions=True)
            await self._pause()

    async def _ready(self) -> bool:
        try:
            await asyncio.wait_for(check_readiness(self._database_probe, self._storage_probe), self._readiness_timeout_seconds)
            return True
        except Exception as error:
            logger.warning("worker_dependency_readiness_failed", extra={"context": {"error_type": type(error).__name__}}); return False

    async def _pause(self) -> None:
        if self._shutdown.is_set(): return
        try: await asyncio.wait_for(self._shutdown.wait(), self._interval_seconds)
        except TimeoutError: pass

    async def _poll_once(self) -> None:
        if self._queue is None or self._shutdown.is_set(): return
        first = self._next_kind; second = "outbox" if first == "job" else "job"; self._next_kind = second
        for kind in (first, second):
            if self._shutdown.is_set(): return
            try:
                claim = self._queue.claim_job if kind == "job" else self._queue.claim_outbox
                item = await claim(worker_id=self._worker_id, lease_seconds=self._lease_seconds)
            except Exception:
                logger.error("worker_claim_failed", extra={"context": {"safe_error_code": "queue_unavailable", "kind": kind}}); continue
            if item is not None:
                if self._shutdown.is_set():
                    logger.info("worker_claim_abandoned", extra={"context": self._context(item, kind, "shutdown_requested")}); return
                await self._process(item, kind); return

    async def _process(self, item: object, kind: str) -> None:
        handler = self._handlers.get(item.type) if kind == "job" else self._outbox_handlers.get(item.topic)
        if handler is None:
            await self._safe_failure(item, kind, "unknown_job_type" if kind == "job" else "unknown_outbox_topic", False); return
        async def invoke() -> None:
            if kind == "job": await handler(item)
            else: await handler(item, item.id)
        handling = asyncio.create_task(invoke()); self._active_handler = handling
        heartbeat = asyncio.create_task(self._heartbeat(item, kind))
        done, _ = await asyncio.wait((handling, heartbeat), return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done and heartbeat.exception() is not None:
            if not handling.done(): handling.cancel()
            try: await asyncio.wait_for(asyncio.shield(handling), self._cancel_timeout_seconds)
            except TimeoutError:
                self._shutdown.set(); self._hard_stop()
                try: await asyncio.wait_for(asyncio.shield(handling), self._cancel_timeout_seconds)
                except (TimeoutError, asyncio.CancelledError): pass
            except asyncio.CancelledError: pass
            self._active_handler = None
            logger.error("worker_lease_lost", extra={"context": self._context(item, kind, "lease_lost")}); return
        heartbeat.cancel(); await asyncio.gather(heartbeat, return_exceptions=True)
        try: await handling
        except RetryableJobError as error: await self._safe_failure(item, kind, error.safe_code, True)
        except PermanentJobError as error: await self._safe_failure(item, kind, error.safe_code, False)
        except asyncio.CancelledError: raise
        except Exception: await self._safe_failure(item, kind, "handler_failed", True)
        else:
            try:
                if kind == "job": await self._queue.succeed(item, self._worker_id)
                else: await self._queue.publish_outbox(item, self._worker_id)
                logger.info("worker_item_succeeded", extra={"context": self._context(item, kind, "succeeded")})
            except Exception: logger.error("worker_completion_rejected", extra={"context": self._context(item, kind, "lease_lost")})
        finally: self._active_handler = None

    async def _heartbeat(self, item: object, kind: str) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            method = self._queue.heartbeat if kind == "job" else self._queue.heartbeat_outbox
            await method(item, self._worker_id, lease_seconds=self._lease_seconds)

    async def _safe_failure(self, item: object, kind: str, code: str, retryable: bool) -> None:
        code = normalize_safe_code(code)
        try:
            method = self._queue.fail if kind == "job" else self._queue.fail_outbox
            await method(item, self._worker_id, safe_code=code, retryable=retryable)
            logger.error("worker_item_failed", extra={"context": self._context(item, kind, code)})
        except Exception: logger.error("worker_failure_record_rejected", extra={"context": self._context(item, kind, "lease_lost")})

    @staticmethod
    def _context(item: object, kind: str, code: str) -> dict[str, object]:
        label = getattr(item, "type", None) if kind == "job" else getattr(item, "topic", None)
        safe_label = label if isinstance(label, str) and TYPE_PATTERN.fullmatch(label) else "internal.type"
        trace = getattr(item, "trace_id", None)
        safe_trace = trace if isinstance(trace, str) and IDENTIFIER_PATTERN.fullmatch(trace) else None
        return {"item_id": str(item.id), "item_type": safe_label, "kind": kind, "attempt": item.attempts, "trace_id": safe_trace, "safe_error_code": normalize_safe_code(code)}


async def _run() -> None:
    from server.app.core.storage import ObjectStorageProbe, create_storage_client
    from server.app.db.session import DatabaseProbe, create_engine
    from server.app.queue.runtime import DatabaseQueueGateway
    from server.app.screening.terminal import screening_terminal_callbacks
    settings = Settings.from_environment(); gateway = DatabaseQueueGateway(settings.database_url,terminal_callbacks=screening_terminal_callbacks()); storage_client=create_storage_client(settings.object_storage_endpoint, settings.object_storage_access_key, settings.object_storage_secret_key, secure=settings.object_storage_secure, connect_timeout_seconds=settings.object_storage_connect_timeout_seconds, read_timeout_seconds=settings.object_storage_read_timeout_seconds, total_timeout_seconds=settings.object_storage_total_timeout_seconds)
    handlers=build_screening_handlers(settings,storage_client,settings.object_storage_bucket)
    worker = Worker(DatabaseProbe(create_engine(settings.database_url)), ObjectStorageProbe(storage_client, settings.object_storage_bucket), interval_seconds=settings.worker_poll_interval_seconds, readiness_timeout_seconds=settings.readiness_timeout_seconds, worker_id=settings.worker_id, lease_seconds=settings.worker_lease_seconds, shutdown_timeout_seconds=settings.worker_shutdown_timeout_seconds, cancel_timeout_seconds=settings.worker_cancel_timeout_seconds, heartbeat_seconds=settings.worker_heartbeat_seconds, queue=gateway, handlers=handlers, outbox_handlers={})
    loop = asyncio.get_running_loop()
    for event in (signal.SIGINT, signal.SIGTERM): loop.add_signal_handler(event, worker.request_shutdown)
    await worker.run()


def main() -> None: configure_logging(); asyncio.run(_run())
if __name__ == "__main__": main()
