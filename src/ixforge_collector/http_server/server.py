from __future__ import annotations

import asyncio

from aiohttp import web

from ixforge_collector.http_server.health import HealthProvider, HealthStatus


class Server:
    """Servidor HTTP con endpoint /health"""

    def __init__(self, address: str, health_provider: HealthProvider) -> None:
        self._address = address
        self._health_provider = health_provider
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ready = asyncio.Event()

        self._app.router.add_get("/health", self._handle_health)

    @property
    def address(self) -> str:
        """Retorna la direccion configurada"""
        return self._address

    def actual_address(self) -> str:
        """Retorna la direccion real del servidor (util cuando se usa puerto 0)"""
        if self._site is not None and self._site._server is not None:
            sockets = getattr(self._site._server, "sockets", None)
            if sockets:
                addr = sockets[0].getsockname()
                return f"{addr[0]}:{addr[1]}"
        return self._address

    async def start(self) -> None:
        """Inicia el servidor HTTP"""
        host, port_str = self._address.rsplit(":", 1)
        port = int(port_str)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()
        self._ready.set()

    async def wait_ready(self, timeout: float = 5.0) -> bool:
        """Espera a que el servidor este listo"""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def shutdown(self) -> None:
        """Detiene el servidor gracefully"""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handler para GET /health"""
        health = self._health_provider.get_health()

        body = _health_to_dict(health)
        status_code = 503 if health.status == "error" else 200

        return web.json_response(body, status=status_code)


def _health_to_dict(health: HealthStatus) -> dict:
    """Convierte HealthStatus a dict para JSON serialization"""
    result: dict = {"status": health.status}

    if health.uptime:
        result["uptime"] = health.uptime

    if health.start_time is not None:
        result["start_time"] = health.start_time.isoformat()

    if health.components:
        comps = {}
        for name, comp in health.components.items():
            c: dict = {"status": comp.status}
            if comp.message:
                c["message"] = comp.message
            if comp.last_run is not None:
                c["last_run"] = comp.last_run.isoformat()
            comps[name] = c
        result["components"] = comps

    return result
