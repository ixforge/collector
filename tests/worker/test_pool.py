import asyncio

from ixforge_collector.worker.pool import run_parallel


class TestRunParallel:
    async def test_empty_items(self) -> None:
        called = False

        async def fn(item: int) -> None:
            nonlocal called
            called = True

        await run_parallel([], 5, fn)
        assert not called

    async def test_all_items_processed(self) -> None:
        results: list[int] = []

        async def fn(item: int) -> None:
            results.append(item)

        await run_parallel([1, 2, 3, 4, 5], 10, fn)
        assert sorted(results) == [1, 2, 3, 4, 5]

    async def test_concurrency_limit(self) -> None:
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def fn(item: int) -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            await asyncio.sleep(0.01)
            async with lock:
                current_concurrent -= 1

        await run_parallel(list(range(10)), 3, fn)
        assert max_concurrent <= 3

    async def test_error_isolation(self) -> None:
        results: list[int] = []

        async def fn(item: int) -> None:
            if item == 3:
                raise ValueError("boom")
            results.append(item)

        # No debe propagar errores
        await run_parallel([1, 2, 3, 4, 5], 5, fn)
        assert 3 not in results
        assert len(results) == 4

    async def test_single_concurrency(self) -> None:
        order: list[int] = []

        async def fn(item: int) -> None:
            order.append(item)
            await asyncio.sleep(0.001)

        await run_parallel([1, 2, 3], 1, fn)
        assert len(order) == 3

    async def test_errors_logged_with_logger(self) -> None:
        from unittest.mock import MagicMock

        logger = MagicMock()
        results: list[int] = []

        async def fn(item: int) -> None:
            if item == 3:
                raise ValueError("boom")
            results.append(item)

        await run_parallel([1, 2, 3, 4, 5], 5, fn, logger=logger)
        # Errores no se propagan
        assert 3 not in results
        assert len(results) == 4
        # Pero se loguean
        logger.warning.assert_called_once()
        call_kwargs = logger.warning.call_args
        assert "boom" in str(call_kwargs)

    async def test_errors_silent_without_logger(self) -> None:
        results: list[int] = []

        async def fn(item: int) -> None:
            if item == 2:
                raise ValueError("silent")
            results.append(item)

        # Sin logger, no crashea
        await run_parallel([1, 2, 3], 5, fn)
        assert len(results) == 2
