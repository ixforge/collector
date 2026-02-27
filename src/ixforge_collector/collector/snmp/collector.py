from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import structlog

from ixforge_collector.collector.snmp.metrics import InterfaceMetrics, InterfacePollResult
from ixforge_collector.collector.snmp.oids import (
    OID_IF_DESCR,
    OID_IF_HC_IN_OCTETS,
    OID_IF_HC_IN_UCAST_PKTS,
    OID_IF_HC_OUT_OCTETS,
    OID_IF_HC_OUT_UCAST_PKTS,
    OID_IF_IN_ERRORS,
    OID_IF_NAME,
    OID_IF_OPER_STATUS,
    OID_IF_OUT_DISCARDS,
    OID_IF_OUT_ERRORS,
    OperStatus,
)
from ixforge_collector.collector.snmp.rate import RateCalculator
from ixforge_collector.config.models import SNMPConfig
from ixforge_collector.core_client.models import MonitoringTargets, PortTarget, SwitchTarget
from ixforge_collector.logging import nop as nop_logger
from ixforge_collector.metrics.victoria import Metric, Writer
from ixforge_collector.worker.pool import run_parallel


@dataclass
class SNMPResult:
    """Resultado de una operacion SNMP"""

    oid: str
    value: object


class SNMPClient(Protocol):
    """Abstrae las operaciones SNMP para permitir mocking"""

    async def walk(self, oid: str) -> list[SNMPResult]: ...
    async def get(self, oids: list[str]) -> list[SNMPResult]: ...
    async def close(self) -> None: ...


class Collector:
    """Implementa el collector SNMP para monitoreo de interfaces"""

    def __init__(
        self,
        cfg: SNMPConfig,
        writer: Writer | None = None,
        targets: MonitoringTargets | None = None,
        client_factory: Any = None,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        self._cfg = cfg
        self._writer = writer
        self._targets = targets or MonitoringTargets()
        self._client_factory = client_factory
        self._rate_calc = RateCalculator()
        self._logger = logger.bind(component="snmp") if logger is not None else nop_logger()

    def name(self) -> str:
        """Retorna el nombre del collector"""
        return "snmp"

    async def collect(self) -> None:
        """Ejecuta una ronda de polling SNMP a todos los switches"""
        targets = self._targets

        if not targets.switches:
            self._logger.debug("no switches to poll")
            return

        # Construir mapa de puertos: "switchID:portName" -> PortTarget
        port_map = _build_port_map(targets.ports)

        # Filtrar switches con SNMP configurado
        pollable = [sw for sw in targets.switches if sw.snmp_community]
        for sw in targets.switches:
            if not sw.snmp_community:
                self._logger.warning(
                    "skipping switch without SNMP community",
                    switch=sw.hostname,
                    switch_id=str(sw.id),
                )

        if not pollable:
            return

        self._logger.debug(
            "starting SNMP poll round",
            switches=len(pollable),
            ports=len(targets.ports),
        )

        all_metrics: list[Metric] = []

        async def poll_one(sw: SwitchTarget) -> None:
            sw_metrics = await self._poll_switch(sw, port_map)
            all_metrics.extend(sw_metrics)

        await run_parallel(pollable, self._cfg.max_concurrency, poll_one)

        if all_metrics and self._writer is not None:
            await self._writer.write_batch(all_metrics)

        self._logger.debug(
            "SNMP poll round complete",
            switches=len(pollable),
            metrics=len(all_metrics),
        )

    async def reconfigure(self, config: Any) -> None:
        """Actualiza la configuracion del collector en caliente"""
        if isinstance(config, MonitoringTargets):
            self._targets = config
            return
        if isinstance(config, SNMPConfig):
            self._cfg = config
            return
        raise TypeError("config must be SNMPConfig or MonitoringTargets")

    async def _poll_switch(
        self,
        sw: SwitchTarget,
        port_map: dict[str, PortTarget],
    ) -> list[Metric]:
        """Hace polling SNMP a un switch individual"""
        if self._client_factory is None:
            self._logger.error("no SNMP client factory configured")
            return []

        client = await self._client_factory(sw)
        if client is None:
            return []

        try:
            return await self._poll_with_client(client, sw, port_map)
        finally:
            await client.close()

    async def _poll_with_client(
        self,
        client: SNMPClient,
        sw: SwitchTarget,
        port_map: dict[str, PortTarget],
    ) -> list[Metric]:
        """Ejecuta el polling usando un cliente SNMP ya creado"""
        if_names = await self._discover_interfaces(client)

        self._logger.debug("discovered interfaces", switch=sw.hostname, count=len(if_names))

        if not if_names:
            return []

        poll_results = await self._poll_interfaces(client, sw, if_names)

        all_metrics: list[Metric] = []
        now = datetime.now()

        for pr in poll_results:
            key = _build_interface_key(str(sw.id), pr.if_name)
            port = port_map.get(key)

            im = InterfaceMetrics(
                switch_hostname=sw.hostname,
                switch_id=str(sw.id),
                if_name=pr.if_name,
                oper_status=pr.oper_status,
                timestamp=now,
            )

            if port is not None:
                im.port_id = str(port.id)
                im.member_id = str(port.member_id) if port.member_id else ""

            # Calcular rates de trafico (octets -> bps)
            in_rate = self._rate_calc.calculate(sw.hostname, pr.if_name, "in_octets", pr.in_octets, now)
            out_rate = self._rate_calc.calculate(sw.hostname, pr.if_name, "out_octets", pr.out_octets, now)

            if in_rate >= 0:
                im.traffic_in_bps = in_rate * 8  # bytes -> bits
            if out_rate >= 0:
                im.traffic_out_bps = out_rate * 8

            # Calcular rates de paquetes
            in_pkt_rate = self._rate_calc.calculate(sw.hostname, pr.if_name, "in_pkts", pr.in_ucast_pkts, now)
            out_pkt_rate = self._rate_calc.calculate(sw.hostname, pr.if_name, "out_pkts", pr.out_ucast_pkts, now)

            if in_pkt_rate >= 0:
                im.packets_in_pps = in_pkt_rate
            if out_pkt_rate >= 0:
                im.packets_out_pps = out_pkt_rate

            # Errores y descartes son valores absolutos, no rates
            im.errors_in = float(pr.in_errors)
            im.errors_out = float(pr.out_errors)
            im.discards_out = float(pr.out_discards)

            # Solo generar metricas si tenemos rates validos
            if in_rate >= 0 or out_rate >= 0:
                all_metrics.extend(im.to_metrics())

        return all_metrics

    async def _discover_interfaces(self, client: SNMPClient) -> dict[int, str]:
        """Hace walk de ifName para descubrir interfaces

        Usa ifDescr como fallback si ifName falla
        """
        base_oid = OID_IF_NAME
        try:
            results = await client.walk(OID_IF_NAME)
        except Exception:
            self._logger.debug("ifName walk failed, trying ifDescr")
            results = await client.walk(OID_IF_DESCR)
            base_oid = OID_IF_DESCR

        if not results:
            return {}

        # Detectar si los resultados vienen de ifDescr
        if "2.2.1.2" in results[0].oid:
            base_oid = OID_IF_DESCR

        if_names: dict[int, str] = {}

        for r in results:
            if_index = _extract_if_index(r.oid, base_oid)
            if if_index is None:
                continue

            if isinstance(r.value, str):
                if_names[if_index] = r.value

        return if_names

    async def _poll_interfaces(
        self,
        client: SNMPClient,
        sw: SwitchTarget,
        if_names: dict[int, str],
    ) -> list[InterfacePollResult]:
        """Obtiene contadores para las interfaces descubiertas usando GET"""
        poll_results: list[InterfacePollResult] = []
        now = datetime.now()

        for if_index, name in if_names.items():
            oids = [
                f"{OID_IF_OPER_STATUS}.{if_index}",
                f"{OID_IF_HC_IN_OCTETS}.{if_index}",
                f"{OID_IF_HC_OUT_OCTETS}.{if_index}",
                f"{OID_IF_HC_IN_UCAST_PKTS}.{if_index}",
                f"{OID_IF_HC_OUT_UCAST_PKTS}.{if_index}",
                f"{OID_IF_IN_ERRORS}.{if_index}",
                f"{OID_IF_OUT_ERRORS}.{if_index}",
                f"{OID_IF_OUT_DISCARDS}.{if_index}",
            ]

            try:
                results = await client.get(oids)
            except Exception:
                self._logger.warning(
                    "failed to get counters for interface",
                    switch=sw.hostname,
                    interface=name,
                )
                continue

            pr = InterfacePollResult(
                switch_hostname=sw.hostname,
                switch_id=str(sw.id),
                if_index=if_index,
                if_name=name,
                timestamp=now,
            )

            for r in results:
                oid = r.oid.lstrip(".")
                _apply_counter_value(pr, oid, r.value)

            poll_results.append(pr)

        return poll_results


def _apply_counter_value(pr: InterfacePollResult, oid: str, val: object) -> None:
    """Asigna un valor de contador al campo correspondiente del poll result"""
    if not isinstance(val, int):
        return

    if oid.startswith(OID_IF_OPER_STATUS):
        pr.oper_status = OperStatus(val) if 1 <= val <= 7 else OperStatus.UNKNOWN
    elif oid.startswith(OID_IF_HC_IN_OCTETS):
        pr.in_octets = val
    elif oid.startswith(OID_IF_HC_OUT_OCTETS):
        pr.out_octets = val
    elif oid.startswith(OID_IF_HC_IN_UCAST_PKTS):
        pr.in_ucast_pkts = val
    elif oid.startswith(OID_IF_HC_OUT_UCAST_PKTS):
        pr.out_ucast_pkts = val
    elif oid.startswith(OID_IF_IN_ERRORS):
        pr.in_errors = val
    elif oid.startswith(OID_IF_OUT_ERRORS):
        pr.out_errors = val
    elif oid.startswith(OID_IF_OUT_DISCARDS):
        pr.out_discards = val


def _build_interface_key(switch_id: str, if_name: str) -> str:
    """Construye la clave para mapear switch+puerto a port"""
    return f"{switch_id}:{if_name}"


def _extract_if_index(full_oid: str, base_oid: str) -> int | None:
    """Extrae el ifIndex del OID completo

    Retorna None si el OID no tiene el formato esperado
    """
    # El OID puede venir con punto inicial
    oid = full_oid.lstrip(".")
    base = base_oid.lstrip(".")
    prefix = base + "."

    if not oid.startswith(prefix):
        return None

    suffix = oid[len(prefix) :]

    if not suffix.isdigit():
        return None

    return int(suffix)


def _build_port_map(ports: list[PortTarget]) -> dict[str, PortTarget]:
    """Construye mapa de 'switchID:portName' -> PortTarget"""
    return {_build_interface_key(str(p.switch_id), p.name): p for p in ports}
