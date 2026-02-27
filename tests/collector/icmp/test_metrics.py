from __future__ import annotations

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from ixforge_collector.collector.icmp.metrics import PingResult


class TestPingResultIpVersion:
    def test_ipv4(self) -> None:
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
        )
        assert pr.ip_version() == "4"

    def test_ipv6(self) -> None:
        pr = PingResult(
            ip=IPv6Address("2001:db8::1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
        )
        assert pr.ip_version() == "6"


class TestPingResultPacketLoss:
    def test_no_loss(self) -> None:
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
        )
        assert pr.packet_loss() == 0.0

    def test_total_loss(self) -> None:
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=0,
        )
        assert pr.packet_loss() == 1.0

    def test_partial_loss(self) -> None:
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=4,
            packets_recv=3,
        )
        assert pr.packet_loss() == 0.25

    def test_zero_sent(self) -> None:
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=0,
            packets_recv=0,
        )
        assert pr.packet_loss() == 1.0


class TestPingResultToMetrics:
    def test_with_responses_generates_six_metrics(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            min_rtt=timedelta(milliseconds=2),
            max_rtt=timedelta(milliseconds=8),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        assert len(metrics) == 6

    def test_without_responses_generates_three_metrics(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=0,
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        assert len(metrics) == 3

    def test_metric_names(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            min_rtt=timedelta(milliseconds=2),
            max_rtt=timedelta(milliseconds=8),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        names = {m.name for m in metrics}
        assert "ixforge_icmp_packets_sent" in names
        assert "ixforge_icmp_packets_received" in names
        assert "ixforge_icmp_packet_loss_ratio" in names
        assert "ixforge_icmp_rtt_seconds" in names
        assert "ixforge_icmp_rtt_min_seconds" in names
        assert "ixforge_icmp_rtt_max_seconds" in names

    def test_metric_values(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            min_rtt=timedelta(milliseconds=2),
            max_rtt=timedelta(milliseconds=8),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        metric_map = {m.name: m.value for m in metrics}
        assert metric_map["ixforge_icmp_packets_sent"] == 3.0
        assert metric_map["ixforge_icmp_packets_received"] == 3.0
        assert metric_map["ixforge_icmp_packet_loss_ratio"] == 0.0
        assert metric_map["ixforge_icmp_rtt_seconds"] == 0.005
        assert metric_map["ixforge_icmp_rtt_min_seconds"] == 0.002
        assert metric_map["ixforge_icmp_rtt_max_seconds"] == 0.008

    def test_metric_labels(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        for m in metrics:
            assert m.labels["ip"] == "10.0.0.1"
            assert m.labels["asn"] == "64512"
            assert m.labels["member_id"] == "uuid-member-1"
            assert m.labels["member_name"] == "Member A"
            assert m.labels["ip_version"] == "4"

    def test_metric_labels_ipv6(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv6Address("2001:db8::1"),
            asn=64512,
            member_id="uuid-member-2",
            member_name="Member B",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=10),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        for m in metrics:
            assert m.labels["ip"] == "2001:db8::1"
            assert m.labels["ip_version"] == "6"
            assert m.labels["member_id"] == "uuid-member-2"
            assert m.labels["member_name"] == "Member B"

    def test_metric_labels_are_independent_copies(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        metrics[0].labels["extra"] = "test"
        assert "extra" not in metrics[1].labels

    def test_metric_timestamp(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        pr = PingResult(
            ip=IPv4Address("10.0.0.1"),
            asn=64512,
            member_id="uuid-member-1",
            member_name="Member A",
            packets_sent=3,
            packets_recv=3,
            rtt=timedelta(milliseconds=5),
            timestamp=ts,
        )
        metrics = pr.to_metrics()
        for m in metrics:
            assert m.timestamp == ts
