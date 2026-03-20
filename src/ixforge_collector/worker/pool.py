from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import structlog


async def run_parallel[T](
    items: list[T],
    max_concurrency: int,
    fn: Callable[[T], Awaitable[None]],
    logger: structlog.stdlib.BoundLogger | None = None,
) -> None:
    """Ejecuta fn para cada item con concurrencia limitada

    Los errores individuales se loguean y no se propagan
    """
    if not items:
        return

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _worker(item: T) -> None:
        async with semaphore:
            await fn(item)

    tasks = [asyncio.create_task(_worker(item)) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, BaseException) and logger is not None:
            logger.warning("parallel task failed", error=str(result))
