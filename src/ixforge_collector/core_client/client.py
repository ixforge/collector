from __future__ import annotations

from uuid import UUID

import httpx
import structlog

from ixforge_collector.config.models import CoreConfig
from ixforge_collector.core_client.models import MemberIP, MonitoringTargets, PortTarget, SwitchTarget
from ixforge_collector.logging import with_component


class CoreClient:
    """Cliente HTTP para la API REST del Core de IXForge"""

    def __init__(self, cfg: CoreConfig, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self._cfg = cfg
        self._log = (
            with_component(logger, "core_client") if logger else structlog.get_logger().bind(component="core_client")
        )
        self._client = httpx.AsyncClient(
            base_url=cfg.url.rstrip("/"),
            headers={"X-API-Key": cfg.api_key},
            timeout=httpx.Timeout(cfg.timeout.total_seconds(), connect=10.0),
        )

    async def fetch_targets(self) -> MonitoringTargets:
        """Obtiene los targets de monitoreo desde el Core"""
        response = await self._client.get("/api/v1/monitoring/targets")
        response.raise_for_status()

        data = response.json()
        return _parse_targets(data)

    async def health_check(self) -> bool:
        """Verifica que el Core este disponible"""
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except httpx.HTTPError as exc:
            self._log.warning("core health check failed", error=str(exc))
            return False

    async def close(self) -> None:
        """Cierra la conexion HTTP"""
        await self._client.aclose()


def _parse_targets(data: dict) -> MonitoringTargets:
    """Parsea la respuesta JSON del Core a DTOs"""
    switches = [
        SwitchTarget(
            id=UUID(sw["id"]),
            hostname=sw["hostname"],
            management_ip=sw.get("management_ip"),
            snmp_community=sw.get("snmp_community"),
        )
        for sw in data.get("switches", [])
    ]

    ports = [
        PortTarget(
            id=UUID(p["id"]),
            switch_id=UUID(p["switch_id"]),
            name=p["name"],
            speed=p["speed"],
            member_id=UUID(p["member_id"]) if p.get("member_id") else None,
        )
        for p in data.get("ports", [])
    ]

    member_ips = [
        MemberIP(
            member_id=UUID(m["member_id"]),
            member_name=m["member_name"],
            address=m["address"],
            af=m["af"],
        )
        for m in data.get("member_ips", [])
    ]

    return MonitoringTargets(switches=switches, ports=ports, member_ips=member_ips)
