import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Protocol

import structlog

from ixforge_collector.collector.icmp.fping import run_fping
from ixforge_collector.collector.icmp.metrics import PingResult
from ixforge_collector.config.models import ICMPConfig
from ixforge_collector.metrics.victoria import Metric, Writer


class TargetProvider(Protocol):
    """Contrato para obtener la lista de targets a monitorear"""

    async def get_targets(self) -> list["Target"]: ...


@dataclass
class Target:
    """Representa un objetivo de ping"""

    ip: IPv4Address | IPv6Address
    asn: int
    member_id: str
    member_name: str


class InvalidConfigError(Exception):
    """Se lanza cuando la configuracion ICMP es invalida"""


def validate_config(cfg: ICMPConfig) -> None:
    """Valida la configuracion ICMP"""
    if cfg.count <= 0:
        raise InvalidConfigError("count must be > 0")
    if cfg.timeout <= timedelta(0):
        raise InvalidConfigError("timeout must be > 0")
    if cfg.max_concurrency <= 0:
        raise InvalidConfigError("max_concurrency must be > 0")


class Collector:
    """Collector ICMP que ejecuta pings con fping y genera metricas"""

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        cfg: ICMPConfig,
        target_provider: TargetProvider,
        writer: Writer,
    ) -> None:
        self._logger = logger.bind(component="icmp") if logger else structlog.get_logger().bind(component="icmp")
        self._cfg = cfg
        self._target_provider = target_provider
        self._writer = writer

    def name(self) -> str:
        """Retorna el nombre unico del collector"""
        return "icmp"

    async def collect(self) -> None:
        """Ejecuta una ronda de pings a todos los targets"""
        targets = await self._target_provider.get_targets()

        if not targets:
            self._logger.debug("no targets to ping")
            return

        self._logger.debug("starting ping round", targets=len(targets))

        results = await self._ping_targets(targets)
        all_metrics: list[Metric] = []

        for result in results:
            all_metrics.extend(result.to_metrics())

        if all_metrics:
            await self._writer.write_batch(all_metrics)

        self._logger.debug("ping round complete", targets=len(targets), metrics=len(all_metrics))

    async def reconfigure(self, config: Any) -> None:
        """Actualiza la configuracion del collector en caliente"""
        if not isinstance(config, ICMPConfig):
            raise TypeError("config must be ICMPConfig")

        validate_config(config)
        self._cfg = config

        self._logger.info(
            "reconfigured",
            count=config.count,
            timeout=config.timeout,
            max_concurrency=config.max_concurrency,
        )

    async def _ping_targets(self, targets: list[Target]) -> list[PingResult]:
        """Ejecuta pings usando fping, separando IPv4 e IPv6"""
        # Separar por version IP
        v4_ips: list[IPv4Address] = []
        v6_ips: list[IPv6Address] = []

        for t in targets:
            if isinstance(t.ip, IPv4Address):
                v4_ips.append(t.ip)
            else:
                v6_ips.append(t.ip)

        # Ejecutar fping en paralelo para v4 y v6
        fping_results: dict[str, Any] = {}
        coros = []
        if v4_ips:
            coros.append(self._run_fping_safe(v4_ips))
        if v6_ips:
            coros.append(self._run_fping_safe(v6_ips))

        for partial in await asyncio.gather(*coros):
            fping_results.update(partial)

        # Convertir resultados de fping a PingResult
        now = datetime.now(UTC)
        ping_results: list[PingResult] = []

        for target in targets:
            ip_str = str(target.ip)
            fping_r = fping_results.get(ip_str)

            pr = PingResult(
                ip=target.ip,
                asn=target.asn,
                member_id=target.member_id,
                member_name=target.member_name,
                timestamp=now,
            )

            if fping_r is not None:
                pr.packets_sent = fping_r.packets_sent
                pr.packets_recv = fping_r.packets_recv
                pr.rtt = timedelta(milliseconds=fping_r.avg_rtt_ms)
                pr.min_rtt = timedelta(milliseconds=fping_r.min_rtt_ms)
                pr.max_rtt = timedelta(milliseconds=fping_r.max_rtt_ms)
            else:
                # fping no retorno resultado para esta IP
                pr.packets_sent = self._cfg.count
                pr.packets_recv = 0

            ping_results.append(pr)

        return ping_results

    async def _run_fping_safe(
        self,
        ips: list[IPv4Address] | list[IPv6Address],
    ) -> dict[str, Any]:
        """Ejecuta fping con manejo de errores"""
        try:
            return await run_fping(
                ips,
                count=self._cfg.count,
                timeout=self._cfg.timeout,
            )
        except Exception as exc:
            self._logger.warning(
                "fping execution failed",
                error=str(exc),
                ip_count=len(ips),
            )
            return {}
