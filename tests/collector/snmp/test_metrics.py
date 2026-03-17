from datetime import UTC, datetime

from ixforge_collector.collector.snmp.metrics import InterfaceMetrics, InterfacePollResult
from ixforge_collector.collector.snmp.oids import OperStatus


class TestOperStatusLabel:
    def test_all_status_labels(self) -> None:
        expected = {
            OperStatus.UP: "up",
            OperStatus.DOWN: "down",
            OperStatus.TESTING: "testing",
            OperStatus.UNKNOWN: "unknown",
            OperStatus.DORMANT: "dormant",
            OperStatus.NOT_PRESENT: "notPresent",
            OperStatus.LOWER_LAYER_DOWN: "lowerLayerDown",
        }
        for status, label in expected.items():
            assert status.label() == label


class TestInterfacePollResult:
    def test_fields_accessible(self) -> None:
        pr = InterfacePollResult(
            switch_name="switch1",
            switch_id="uuid-1",
            if_index=10,
            if_name="GE0/0/1",
            port_id="uuid-port-5",
            oper_status=OperStatus.UP,
            in_octets=1000000,
            out_octets=500000,
            in_ucast_pkts=10000,
            out_ucast_pkts=5000,
            in_errors=1,
            out_errors=2,
            out_discards=3,
            timestamp=datetime.now(tz=UTC),
        )
        assert pr.switch_name == "switch1"
        assert pr.if_index == 10
        assert pr.in_octets == 1000000

    def test_default_values(self) -> None:
        pr = InterfacePollResult(
            switch_name="switch1",
            switch_id="uuid-1",
            if_index=1,
            if_name="eth0",
        )
        assert pr.port_id == ""
        assert pr.oper_status == OperStatus.UNKNOWN
        assert pr.in_octets == 0
        assert pr.timestamp is None


class TestInterfaceMetrics:
    def test_to_metrics_generates_eight(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        im = InterfaceMetrics(
            switch_name="switch1.example.com",
            switch_id="uuid-1",
            if_name="GE0/0/1",
            port_id="uuid-port-10",
            member_id="uuid-member-5",
            asn=64512,
            oper_status=OperStatus.UP,
            traffic_in_bps=1_000_000_000,
            traffic_out_bps=500_000_000,
            packets_in_pps=100_000,
            packets_out_pps=50_000,
            errors_in=10,
            errors_out=5,
            discards_out=2,
            timestamp=ts,
        )
        metrics = im.to_metrics()
        assert len(metrics) == 8

    def test_to_metrics_values(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        im = InterfaceMetrics(
            switch_name="switch1.example.com",
            switch_id="uuid-1",
            if_name="GE0/0/1",
            port_id="uuid-port-10",
            member_id="uuid-member-5",
            asn=64512,
            oper_status=OperStatus.UP,
            traffic_in_bps=1_000_000_000,
            traffic_out_bps=500_000_000,
            packets_in_pps=100_000,
            packets_out_pps=50_000,
            errors_in=10,
            errors_out=5,
            discards_out=2,
            timestamp=ts,
        )
        metrics = im.to_metrics()
        metric_map = {m.name: m.value for m in metrics}
        assert metric_map["ixforge_interface_traffic_in_bps"] == 1_000_000_000
        assert metric_map["ixforge_interface_traffic_out_bps"] == 500_000_000
        assert metric_map["ixforge_interface_packets_in_pps"] == 100_000
        assert metric_map["ixforge_interface_packets_out_pps"] == 50_000
        assert metric_map["ixforge_interface_errors_in"] == 10
        assert metric_map["ixforge_interface_errors_out"] == 5
        assert metric_map["ixforge_interface_discards_out"] == 2
        assert metric_map["ixforge_interface_oper_status"] == 1

    def test_to_metrics_labels(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        im = InterfaceMetrics(
            switch_name="switch1.example.com",
            switch_id="uuid-1",
            if_name="GE0/0/1",
            port_id="uuid-port-5",
            member_id="uuid-member-3",
            asn=64512,
            oper_status=OperStatus.UP,
            timestamp=ts,
        )
        metrics = im.to_metrics()
        for m in metrics:
            assert m.labels["switch_name"] == "switch1.example.com"
            assert m.labels["ifname"] == "GE0/0/1"
            assert m.labels["switch_id"] == "uuid-1"
            assert m.labels["port_id"] == "uuid-port-5"
            assert m.labels["member_id"] == "uuid-member-3"
            assert m.labels["asn"] == "64512"

    def test_to_metrics_labels_are_independent_copies(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        im = InterfaceMetrics(
            switch_name="switch1",
            switch_id="uuid-1",
            if_name="eth0",
            timestamp=ts,
        )
        metrics = im.to_metrics()
        metrics[0].labels["extra"] = "test"
        assert "extra" not in metrics[1].labels

    def test_to_metrics_timestamp(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        im = InterfaceMetrics(
            switch_name="switch1",
            switch_id="uuid-1",
            if_name="eth0",
            timestamp=ts,
        )
        metrics = im.to_metrics()
        for m in metrics:
            assert m.timestamp == ts
