from uuid import UUID

from ixforge_collector.core_client.models import MemberIP, MonitoringTargets, PortTarget, SwitchTarget


class TestSwitchTarget:
    def test_create(self) -> None:
        sw = SwitchTarget(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            hostname="switch1",
            management_ip="10.0.0.1",
            snmp_community="public",
        )
        assert sw.hostname == "switch1"
        assert sw.management_ip == "10.0.0.1"

    def test_optional_fields(self) -> None:
        sw = SwitchTarget(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            hostname="switch1",
            management_ip=None,
            snmp_community=None,
        )
        assert sw.management_ip is None
        assert sw.snmp_community is None


class TestPortTarget:
    def test_create(self) -> None:
        pt = PortTarget(
            id=UUID("00000000-0000-0000-0000-000000000010"),
            switch_id=UUID("00000000-0000-0000-0000-000000000001"),
            name="GE0/0/1",
            speed=1000,
            member_id=UUID("00000000-0000-0000-0000-000000000005"),
        )
        assert pt.name == "GE0/0/1"
        assert pt.speed == 1000

    def test_optional_member(self) -> None:
        pt = PortTarget(
            id=UUID("00000000-0000-0000-0000-000000000010"),
            switch_id=UUID("00000000-0000-0000-0000-000000000001"),
            name="GE0/0/1",
            speed=1000,
            member_id=None,
        )
        assert pt.member_id is None


class TestMemberIP:
    def test_create(self) -> None:
        m = MemberIP(
            member_id=UUID("00000000-0000-0000-0000-000000000005"),
            member_name="ISP1",
            address="10.0.0.50",
            af=4,
        )
        assert m.member_name == "ISP1"
        assert m.af == 4


class TestMonitoringTargets:
    def test_defaults_empty(self) -> None:
        mt = MonitoringTargets()
        assert mt.switches == []
        assert mt.ports == []
        assert mt.member_ips == []

    def test_with_data(self) -> None:
        sw = SwitchTarget(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            hostname="sw1",
            management_ip="10.0.0.1",
            snmp_community="public",
        )
        mt = MonitoringTargets(switches=[sw])
        assert len(mt.switches) == 1
