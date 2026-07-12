from collections.abc import Awaitable, Callable, Mapping
from server.app.queue.service import PermanentJobError, RetryableJobError


class OutboxDispatcher:
    """Dispatches durable events only through an explicit topic registry."""
    def __init__(self, gateway: object, handlers: Mapping[str, Callable[[object], Awaitable[None]]]) -> None:
        self._gateway = gateway
        self._handlers = dict(handlers)

    async def dispatch(self, event: object) -> None:
        handler = self._handlers.get(event.topic)
        if handler is None:
            await self._gateway.fail_outbox(event, safe_code="unknown_outbox_topic", retryable=False)
            return
        try:
            await handler(event)
        except RetryableJobError as error:
            await self._gateway.fail_outbox(event, safe_code=error.safe_code, retryable=True)
        except PermanentJobError as error:
            await self._gateway.fail_outbox(event, safe_code=error.safe_code, retryable=False)
        except Exception:
            await self._gateway.fail_outbox(event, safe_code="outbox_handler_failed", retryable=True)
        else:
            await self._gateway.publish_outbox(event)
