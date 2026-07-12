import asyncio

from server.app.worker.main import Worker


class CountingProbe:
    def __init__(self) -> None:
        self.calls = 0

    async def check(self) -> None:
        self.calls += 1


class FlakyProbe(CountingProbe):
    async def check(self) -> None:
        await super().check()
        if self.calls == 1:
            raise RuntimeError("dependency unavailable")


def test_worker_stops_after_shutdown_request() -> None:
    database = CountingProbe()
    storage = CountingProbe()
    worker = Worker(database, storage, interval_seconds=0)

    async def exercise() -> None:
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(0)
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(exercise())

    assert database.calls >= 1
    assert storage.calls >= 1


def test_worker_keeps_running_when_a_readiness_check_fails() -> None:
    database = FlakyProbe()
    storage = CountingProbe()
    worker = Worker(database, storage, interval_seconds=0)

    async def exercise() -> None:
        task = asyncio.create_task(worker.run())
        while database.calls < 2:
            await asyncio.sleep(0)
        worker.request_shutdown()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(exercise())

    assert database.calls >= 2
    assert storage.calls >= 1
