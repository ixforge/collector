import asyncio
from collections.abc import Awaitable, Callable


async def run_parallel[T](
    items: list[T],
    max_concurrency: int,
    fn: Callable[[T], Awaitable[None]],
) -> None:
    """Ejecuta fn para cada item con concurrencia limitada

    Los errores individuales son manejados por fn (no se acumulan)
    """
    if not items:
        return

    semaphore = asyncio.Semaphore(max_concurrency)

    async def _worker(item: T) -> None:
        async with semaphore:
            await fn(item)

    tasks = [asyncio.create_task(_worker(item)) for item in items]
    await asyncio.gather(*tasks, return_exceptions=True)
