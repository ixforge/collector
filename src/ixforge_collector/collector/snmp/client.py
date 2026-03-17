from __future__ import annotations

from typing import TYPE_CHECKING

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulk_walk_cmd,
    get_cmd,
)
from pysnmp.proto.rfc1902 import Counter32, Counter64, Gauge32, Integer, Integer32, Unsigned32

from ixforge_collector.collector.snmp.collector import SNMPClient, SNMPResult
from ixforge_collector.config.models import SNMPConfig

if TYPE_CHECKING:
    from ixforge_collector.core_client.models import SwitchTarget


async def new_snmp_client(cfg: SNMPConfig, sw: SwitchTarget) -> SNMPClient:
    """Crea un nuevo cliente SNMP para el switch especificado"""
    if not sw.management_ip:
        raise ValueError(f"switch {sw.name} has no management IP")
    if not sw.snmp_community:
        raise ValueError(f"switch {sw.name} has no SNMP community")

    timeout_secs = int(cfg.timeout.total_seconds())

    transport = await UdpTransportTarget.create(
        (str(sw.management_ip), 161),
        timeout=timeout_secs,
        retries=cfg.retries,
    )

    return _PySNMPClient(
        community=sw.snmp_community,
        transport=transport,
        max_repetitions=cfg.max_repetitions,
    )


class _PySNMPClient:
    """Implementacion de SNMPClient usando pysnmp"""

    def __init__(
        self,
        community: str,
        transport: UdpTransportTarget,
        max_repetitions: int,
    ) -> None:
        self._community = community
        self._transport = transport
        self._max_repetitions = max_repetitions
        self._engine = SnmpEngine()

    async def walk(self, oid: str) -> list[SNMPResult]:
        """Ejecuta SNMP GETBULK (walk) para el OID especificado"""
        results: list[SNMPResult] = []

        iterator = bulk_walk_cmd(
            self._engine,
            CommunityData(self._community),
            self._transport,
            ContextData(),
            0,  # non-repeaters
            self._max_repetitions,
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        )

        async for error_indication, error_status, error_index, var_binds in iterator:
            if error_indication:
                raise RuntimeError(f"SNMP error: {error_indication}")
            if error_status:
                raise RuntimeError(f"SNMP error: {error_status.prettyPrint()} at {error_index}")

            for var_bind in var_binds:
                oid_str = ".".join(str(x) for x in var_bind[0].asTuple())
                value = _to_native(var_bind[1])
                results.append(SNMPResult(oid=oid_str, value=value))

        return results

    async def get(self, oids: list[str]) -> list[SNMPResult]:
        """Ejecuta SNMP GET para los OIDs especificados"""
        results: list[SNMPResult] = []

        object_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]

        error_indication, error_status, error_index, var_binds = await get_cmd(
            self._engine,
            CommunityData(self._community),
            self._transport,
            ContextData(),
            *object_types,
        )

        if error_indication:
            raise RuntimeError(f"SNMP error: {error_indication}")
        if error_status:
            raise RuntimeError(f"SNMP error: {error_status.prettyPrint()} at {error_index}")

        for var_bind in var_binds:
            oid_str = ".".join(str(x) for x in var_bind[0].asTuple())
            value = _to_native(var_bind[1])
            results.append(SNMPResult(oid=oid_str, value=value))

        return results

    async def close(self) -> None:
        """Cierra la conexion SNMP"""
        self._engine.close_dispatcher()


# Tipos SNMP numericos que deben convertirse a int nativo
_INTEGER_TYPES = (Counter32, Counter64, Gauge32, Integer, Integer32, Unsigned32)


def _to_native(val: object) -> int | str:
    """Convierte un valor SNMP a tipo nativo Python

    Los contadores y gauges se convierten a int,
    todo lo demas a str via prettyPrint()
    """
    if isinstance(val, _INTEGER_TYPES):
        return int(val)
    return val.prettyPrint()  # type: ignore[attr-defined]
