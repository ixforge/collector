import asyncio
import io
from datetime import timedelta

import pytest

from ixforge_collector.logging import setup
from ixforge_collector.scheduler.scheduler import Scheduler


class FakeCollector:
    def __init__(self, collector_name: str = "fake", fail: bool = False) -> None:
        self._name = collector_name
        self._fail = fail
        self.call_count = 0

    def name(self) -> str:
        return self._name

    async def collect(self) -> None:
        self.call_count += 1
        if self._fail:
            raise RuntimeError("collector error")

    async def reconfigure(self, config: object) -> None:
        pass


class TestScheduler:
    def _make_scheduler(self) -> Scheduler:
        logger = setup("info", io.StringIO())
        return Scheduler(logger)

    async def test_register_and_start(self) -> None:
        s = self._make_scheduler()
        c = FakeCollector()
        s.register(c, timedelta(seconds=60))

        await s.start()
        # Esperar a que se ejecute al menos una vez (inmediata)
        await asyncio.sleep(0.05)
        assert c.call_count >= 1
        assert s.is_running()
        await s.stop()

    async def test_stop_idempotent(self) -> None:
        s = self._make_scheduler()
        await s.stop()
        await s.stop()

    async def test_start_twice_raises(self) -> None:
        s = self._make_scheduler()
        c = FakeCollector()
        s.register(c, timedelta(seconds=60))
        await s.start()

        with pytest.raises(RuntimeError, match="already started"):
            await s.start()

        await s.stop()

    async def test_get_last_run(self) -> None:
        s = self._make_scheduler()
        c = FakeCollector()
        s.register(c, timedelta(seconds=60))

        assert s.get_last_run("fake") is None

        await s.start()
        await asyncio.sleep(0.05)
        assert s.get_last_run("fake") is not None
        await s.stop()

    async def test_get_last_run_unknown_collector(self) -> None:
        s = self._make_scheduler()
        assert s.get_last_run("nonexistent") is None

    async def test_is_running(self) -> None:
        s = self._make_scheduler()
        assert not s.is_running()
        c = FakeCollector()
        s.register(c, timedelta(seconds=60))
        await s.start()
        assert s.is_running()
        await s.stop()
        assert not s.is_running()

    async def test_error_isolation(self) -> None:
        s = self._make_scheduler()
        failing = FakeCollector("failing", fail=True)
        good = FakeCollector("good")

        s.register(failing, timedelta(seconds=0.05))
        s.register(good, timedelta(seconds=0.05))

        await s.start()
        await asyncio.sleep(0.15)

        # Ambos deben haberse ejecutado a pesar del error
        assert failing.call_count >= 1
        assert good.call_count >= 1
        await s.stop()

    async def test_collectors(self) -> None:
        s = self._make_scheduler()
        c1 = FakeCollector("c1")
        c2 = FakeCollector("c2")
        s.register(c1, timedelta(seconds=60))
        s.register(c2, timedelta(seconds=60))

        collectors = s.collectors()
        assert "c1" in collectors
        assert "c2" in collectors
