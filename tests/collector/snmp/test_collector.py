from __future__ import annotations

from uuid import UUID

import pytest

from ixforge_collector.collector.snmp.collector import (
    Collector,
    SNMPResult,
    _build_interface_key,
    _build_port_map,
    _extract_if_index,
)
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
from ixforge_collector.config.models import SNMPConfig
from ixforge_collector.core_client.models import MonitoringTargets, PortTarget, SwitchTarget


class MockSNMPClient:
    def __init__(self, walk_results=None, get_results=None, walk_error=None, get_error=None):
        self.walk_results = walk_results or {}
        self.get_results = get_results or {}
        self.walk_error = walk_error
        self.get_error = get_error
        self.closed = False

    async def walk(self, oid):
        if self.walk_error is not None:
            raise self.walk_error
        return self.walk_results.get(oid, [])

    async def get(self, oids):
        if self.get_error is not None:
            raise self.get_error
        return [self.get_results[oid] for oid in oids if oid in self.get_results]

    async def close(self):
        self.closed = True


class MockSNMPClientWithFallback:
    def __init__(self, walk_results=None, get_results=None, fail_oids=None):
        self.walk_results = walk_results or {}
        self.get_results = get_results or {}
        self.fail_oids = fail_oids or set()

    async def walk(self, oid):
        if oid in self.fail_oids:
            raise RuntimeError(f"SNMP walk failed for {oid}")
        return self.walk_results.get(oid, [])

    async def get(self, oids):
        results = []
        for oid in oids:
            if oid not in self.fail_oids and oid in self.get_results:
                results.append(self.get_results[oid])
        return results

    async def close(self):
        pass


_TEST_UUID = UUID("00000000-0000-0000-0000-000000000001")
_TEST_UUID_2 = UUID("00000000-0000-0000-0000-000000000002")


def _make_switch(
    switch_id: UUID = _TEST_UUID,
    hostname: str = "switch1",
    snmp_community: str = "public",
) -> SwitchTarget:
    return SwitchTarget(
        id=switch_id,
        hostname=hostname,
        management_ip="10.0.0.1",
        snmp_community=snmp_community,
    )


class TestCollectorName:
    def test_name_returns_snmp(self) -> None:
        c = Collector(cfg=SNMPConfig())
        assert c.name() == "snmp"


class TestCollectorCollect:
    async def test_collect_empty_switches(self) -> None:
        c = Collector(
            cfg=SNMPConfig(),
            targets=MonitoringTargets(switches=[]),
        )
        await c.collect()

    async def test_collect_skips_switches_without_community(self) -> None:
        sw = _make_switch(snmp_community="")
        targets = MonitoringTargets(switches=[sw])
        c = Collector(cfg=SNMPConfig(), targets=targets)
        await c.collect()


class TestCollectorReconfigure:
    async def test_reconfigure_with_valid_config(self) -> None:
        c = Collector(cfg=SNMPConfig())
        new_cfg = SNMPConfig(max_concurrency=10)
        await c.reconfigure(new_cfg)
        assert c._cfg.max_concurrency == 10

    async def test_reconfigure_with_targets(self) -> None:
        c = Collector(cfg=SNMPConfig())
        new_targets = MonitoringTargets(switches=[_make_switch()])
        await c.reconfigure(new_targets)
        assert len(c._targets.switches) == 1

    async def test_reconfigure_with_invalid_type(self) -> None:
        c = Collector(cfg=SNMPConfig())
        with pytest.raises(TypeError):
            await c.reconfigure("invalid")


class TestDiscoverInterfaces:
    async def test_discover_interfaces(self) -> None:
        mock_client = MockSNMPClient(
            walk_results={
                OID_IF_NAME: [
                    SNMPResult(oid=f"{OID_IF_NAME}.1", value="GigabitEthernet0/0/1"),
                    SNMPResult(oid=f"{OID_IF_NAME}.2", value="GigabitEthernet0/0/2"),
                    SNMPResult(oid=f"{OID_IF_NAME}.10", value="Vlan100"),
                ],
            },
        )
        c = Collector(cfg=SNMPConfig())
        if_names = await c._discover_interfaces(mock_client)
        assert len(if_names) == 3
        assert if_names[1] == "GigabitEthernet0/0/1"
        assert if_names[2] == "GigabitEthernet0/0/2"
        assert if_names[10] == "Vlan100"

    async def test_discover_interfaces_fallback_to_if_descr(self) -> None:
        mock_client = MockSNMPClientWithFallback(
            walk_results={
                OID_IF_DESCR: [
                    SNMPResult(oid=f"{OID_IF_DESCR}.1", value="FastEthernet0/1"),
                    SNMPResult(oid=f"{OID_IF_DESCR}.2", value="FastEthernet0/2"),
                ],
            },
            fail_oids={OID_IF_NAME},
        )
        c = Collector(cfg=SNMPConfig())
        if_names = await c._discover_interfaces(mock_client)
        assert len(if_names) == 2
        assert if_names[1] == "FastEthernet0/1"

    async def test_discover_interfaces_error(self) -> None:
        mock_client = MockSNMPClient(walk_error=RuntimeError("SNMP timeout"))
        c = Collector(cfg=SNMPConfig())
        with pytest.raises(RuntimeError, match="SNMP timeout"):
            await c._discover_interfaces(mock_client)

    async def test_discover_interfaces_with_leading_dot(self) -> None:
        mock_client = MockSNMPClient(
            walk_results={
                OID_IF_NAME: [
                    SNMPResult(oid=f".{OID_IF_NAME}.5", value="eth0"),
                ],
            },
        )
        c = Collector(cfg=SNMPConfig())
        if_names = await c._discover_interfaces(mock_client)
        assert if_names[5] == "eth0"


class TestPollInterfaces:
    async def test_poll_interfaces(self) -> None:
        mock_client = MockSNMPClient(
            get_results={
                f"{OID_IF_OPER_STATUS}.1": SNMPResult(oid=f"{OID_IF_OPER_STATUS}.1", value=1),
                f"{OID_IF_HC_IN_OCTETS}.1": SNMPResult(oid=f"{OID_IF_HC_IN_OCTETS}.1", value=1000000),
                f"{OID_IF_HC_OUT_OCTETS}.1": SNMPResult(oid=f"{OID_IF_HC_OUT_OCTETS}.1", value=500000),
                f"{OID_IF_HC_IN_UCAST_PKTS}.1": SNMPResult(oid=f"{OID_IF_HC_IN_UCAST_PKTS}.1", value=10000),
                f"{OID_IF_HC_OUT_UCAST_PKTS}.1": SNMPResult(oid=f"{OID_IF_HC_OUT_UCAST_PKTS}.1", value=5000),
                f"{OID_IF_IN_ERRORS}.1": SNMPResult(oid=f"{OID_IF_IN_ERRORS}.1", value=5),
                f"{OID_IF_OUT_ERRORS}.1": SNMPResult(oid=f"{OID_IF_OUT_ERRORS}.1", value=2),
                f"{OID_IF_OUT_DISCARDS}.1": SNMPResult(oid=f"{OID_IF_OUT_DISCARDS}.1", value=1),
            },
        )
        sw = _make_switch(hostname="switch1.example.com")
        if_names = {1: "GigabitEthernet0/0/1"}
        c = Collector(cfg=SNMPConfig())
        results = await c._poll_interfaces(mock_client, sw, if_names)
        assert len(results) == 1
        pr = results[0]
        assert pr.if_name == "GigabitEthernet0/0/1"
        assert pr.oper_status == OperStatus.UP
        assert pr.in_octets == 1000000
        assert pr.out_octets == 500000
        assert pr.in_errors == 5
        assert pr.out_errors == 2
        assert pr.out_discards == 1

    async def test_poll_interfaces_continues_on_error(self) -> None:
        mock_client = MockSNMPClientWithFallback(
            get_results={
                f"{OID_IF_OPER_STATUS}.2": SNMPResult(oid=f"{OID_IF_OPER_STATUS}.2", value=1),
                f"{OID_IF_HC_IN_OCTETS}.2": SNMPResult(oid=f"{OID_IF_HC_IN_OCTETS}.2", value=1000),
                f"{OID_IF_HC_OUT_OCTETS}.2": SNMPResult(oid=f"{OID_IF_HC_OUT_OCTETS}.2", value=500),
                f"{OID_IF_HC_IN_UCAST_PKTS}.2": SNMPResult(oid=f"{OID_IF_HC_IN_UCAST_PKTS}.2", value=100),
                f"{OID_IF_HC_OUT_UCAST_PKTS}.2": SNMPResult(oid=f"{OID_IF_HC_OUT_UCAST_PKTS}.2", value=50),
                f"{OID_IF_IN_ERRORS}.2": SNMPResult(oid=f"{OID_IF_IN_ERRORS}.2", value=0),
                f"{OID_IF_OUT_ERRORS}.2": SNMPResult(oid=f"{OID_IF_OUT_ERRORS}.2", value=0),
                f"{OID_IF_OUT_DISCARDS}.2": SNMPResult(oid=f"{OID_IF_OUT_DISCARDS}.2", value=0),
            },
            fail_oids={f"{OID_IF_OPER_STATUS}.1"},
        )
        sw = _make_switch()
        if_names = {1: "eth0", 2: "eth1"}
        c = Collector(cfg=SNMPConfig())
        results = await c._poll_interfaces(mock_client, sw, if_names)
        found_eth1 = any(r.if_name == "eth1" for r in results)
        assert found_eth1


class TestHelperFunctions:
    def test_build_interface_key(self) -> None:
        assert _build_interface_key("uuid-1", "GE0/0/1") == "uuid-1:GE0/0/1"

    def test_extract_if_index_normal(self) -> None:
        result = _extract_if_index("1.3.6.1.2.1.2.2.1.2.10", "1.3.6.1.2.1.2.2.1.2")
        assert result == 10

    def test_extract_if_index_with_leading_dot(self) -> None:
        result = _extract_if_index(".1.3.6.1.2.1.31.1.1.1.6.25", "1.3.6.1.2.1.31.1.1.1.6")
        assert result == 25

    def test_extract_if_index_no_suffix(self) -> None:
        result = _extract_if_index("1.3.6.1.2.1.2.2.1.2", "1.3.6.1.2.1.2.2.1.2")
        assert result is None

    def test_extract_if_index_non_numeric_suffix(self) -> None:
        result = _extract_if_index("1.3.6.1.2.1.2.2.1.2.abc", "1.3.6.1.2.1.2.2.1.2")
        assert result is None

    def test_build_port_map(self) -> None:
        ports = [
            PortTarget(
                id=UUID("00000000-0000-0000-0000-000000000010"),
                switch_id=_TEST_UUID,
                name="GE0/0/1",
                speed=1000,
                member_id=UUID("00000000-0000-0000-0000-000000000005"),
            ),
        ]
        result = _build_port_map(ports)
        key = f"{_TEST_UUID}:GE0/0/1"
        assert key in result
        assert result[key].id == UUID("00000000-0000-0000-0000-000000000010")
