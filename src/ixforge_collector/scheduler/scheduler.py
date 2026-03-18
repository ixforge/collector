import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from ixforge_collector.logging import with_component


class Scheduler:
    """Orquesta la ejecucion periodica de collectors"""

    def __init__(self, logger: structlog.stdlib.BoundLogger) -> None:
        self._logger = with_component(logger, "scheduler")
        self._tasks: dict[str, _Task] = {}
        self._running = False
        self._async_tasks: list[asyncio.Task[None]] = []

    def register(self, collector: Any, interval: timedelta) -> None:
        """Registra un collector para ser ejecutado con el intervalo especificado

        Debe llamarse antes de start
        """
        name = collector.name()
        self._tasks[name] = _Task(collector, interval)
        self._logger.info("registered collector", collector=name, interval=str(interval))

    async def start(self) -> None:
        """Inicia la ejecucion de todos los collectors registrados"""
        if self._running:
            raise RuntimeError("scheduler already started")

        self._running = True
        self._logger.info("starting scheduler", collectors=len(self._tasks))

        for task in self._tasks.values():
            async_task = asyncio.create_task(task.loop(self._logger))
            self._async_tasks.append(async_task)

    async def stop(self) -> None:
        """Detiene todos los collectors"""
        if not self._running:
            return

        self._logger.info("stopping scheduler")

        for task in self._async_tasks:
            task.cancel()

        await asyncio.gather(*self._async_tasks, return_exceptions=True)
        self._async_tasks.clear()
        self._running = False

        self._logger.info("scheduler stopped")

    def get_last_run(self, name: str) -> datetime | None:
        """Retorna el timestamp de la ultima ejecucion de un collector"""
        task = self._tasks.get(name)
        if task is None:
            return None
        return task.last_run

    def is_running(self) -> bool:
        return self._running

    def collectors(self) -> dict[str, Any]:
        """Retorna los collectors registrados"""
        return {name: t.collector for name, t in self._tasks.items()}


class _Task:
    """Representa una tarea programada para un collector"""

    def __init__(self, collector: Any, interval: timedelta) -> None:
        self.collector = collector
        self.interval = interval
        self.last_run: datetime | None = None

    async def _run(self, logger: structlog.stdlib.BoundLogger) -> None:
        """Ejecuta el collector y registra errores"""
        name = self.collector.name()
        start = datetime.now(UTC)

        try:
            await self.collector.collect()
        except Exception:
            duration = datetime.now(UTC) - start
            self.last_run = datetime.now(UTC)
            logger.error("collector failed", collector=name, duration=str(duration), exc_info=True)
            return

        duration = datetime.now(UTC) - start
        self.last_run = datetime.now(UTC)
        logger.debug("collector completed", collector=name, duration=str(duration))

    async def loop(self, logger: structlog.stdlib.BoundLogger) -> None:
        """Ejecuta el collector periodicamente hasta que se cancele"""
        name = self.collector.name()
        logger.info("starting collector loop", collector=name, interval=str(self.interval))

        # Ejecutar inmediatamente al iniciar
        await self._run(logger)

        try:
            while True:
                await asyncio.sleep(self.interval.total_seconds())
                await self._run(logger)
        except asyncio.CancelledError:
            logger.info("stopping collector loop", collector=name)
