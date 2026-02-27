from datetime import UTC, datetime

import aiohttp
import pytest
from aiohttp import web

from ixforge_collector.http_server.health import ComponentHealth, HealthStatus
from ixforge_collector.http_server.server import Server, _health_to_dict


class FakeHealthProvider:
    """Mock del HealthProvider para tests"""

    def __init__(self, status: HealthStatus | None = None) -> None:
        self._status = status or HealthStatus(status="ok")

    def get_health(self) -> HealthStatus:
        return self._status


class TestHealthToDict:
    def test_minimal(self) -> None:
        hs = HealthStatus(status="ok")
        result = _health_to_dict(hs)
        assert result == {"status": "ok"}

    def test_with_uptime(self) -> None:
        hs = HealthStatus(status="ok", uptime="1h30m0s")
        result = _health_to_dict(hs)
        assert result["uptime"] == "1h30m0s"

    def test_with_start_time(self) -> None:
        now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        hs = HealthStatus(status="ok", start_time=now)
        result = _health_to_dict(hs)
        assert "start_time" in result

    def test_with_components(self) -> None:
        now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        hs = HealthStatus(
            status="ok",
            components={
                "core": ComponentHealth(status="ok"),
                "icmp": ComponentHealth(status="ok", last_run=now),
                "scheduler": ComponentHealth(status="running", message="3 tasks"),
            },
        )
        result = _health_to_dict(hs)
        assert result["components"]["core"] == {"status": "ok"}
        assert "last_run" in result["components"]["icmp"]
        assert result["components"]["scheduler"]["message"] == "3 tasks"

    def test_omits_empty_fields(self) -> None:
        hs = HealthStatus(status="ok")
        result = _health_to_dict(hs)
        assert "uptime" not in result
        assert "start_time" not in result
        assert "components" not in result


async def _make_test_server(provider: FakeHealthProvider) -> tuple[aiohttp.ClientSession, int, web.AppRunner]:
    """Crea un servidor de prueba y retorna session, puerto y runner para cleanup"""
    server = Server("127.0.0.1:0", provider)
    runner = web.AppRunner(server._app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    sockets = site._server.sockets
    port = sockets[0].getsockname()[1]

    session = aiohttp.ClientSession()
    return session, port, runner


class TestServer:
    @pytest.fixture
    async def server_and_client(self):
        provider = FakeHealthProvider(
            HealthStatus(
                status="ok",
                uptime="10s",
                components={"core": ComponentHealth(status="ok")},
            )
        )
        session, port, runner = await _make_test_server(provider)
        yield session, port
        await session.close()
        await runner.cleanup()

    async def test_health_returns_200(self, server_and_client) -> None:
        session, port = server_and_client
        async with session.get(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert "components" in data

    async def test_health_error_returns_503(self) -> None:
        provider = FakeHealthProvider(HealthStatus(status="error"))
        session, port, runner = await _make_test_server(provider)
        try:
            async with session.get(f"http://127.0.0.1:{port}/health") as resp:
                assert resp.status == 503
                data = await resp.json()
                assert data["status"] == "error"
        finally:
            await session.close()
            await runner.cleanup()

    async def test_health_method_not_allowed(self) -> None:
        provider = FakeHealthProvider()
        session, port, runner = await _make_test_server(provider)
        try:
            async with session.post(f"http://127.0.0.1:{port}/health") as resp:
                # aiohttp router returns 405 for unsupported methods automatically
                assert resp.status == 405
        finally:
            await session.close()
            await runner.cleanup()

    async def test_start_and_shutdown(self) -> None:
        provider = FakeHealthProvider()
        server = Server("127.0.0.1:0", provider)
        await server.start()
        assert await server.wait_ready(timeout=2.0)
        await server.shutdown()

    async def test_wait_ready_timeout(self) -> None:
        provider = FakeHealthProvider()
        server = Server("127.0.0.1:0", provider)
        # Never start - should timeout
        result = await server.wait_ready(timeout=0.1)
        assert result is False
