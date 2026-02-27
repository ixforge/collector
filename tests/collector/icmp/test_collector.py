from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address
from unittest.mock import AsyncMock, patch

import pytest

from ixforge_collector.collector.icmp.collector import (
    Collector,
    InvalidConfigError,
    Target,
    validate_config,
)
from ixforge_collector.collector.icmp.fping import FpingResult
from ixforge_collector.config.models import ICMPConfig


def _make_target(
    ip: str = "10.0.0.1",
    asn: int = 64512,
    member_id: str = "uuid-member-1",
    member_name: str = "Member A",
) -> Target:
    addr = IPv4Address(ip) if ":" not in ip else IPv6Address(ip)
    return Target(
        ip=addr,
        asn=asn,
        member_id=member_id,
        member_name=member_name,
    )


class MockTargetProvider:
    def __init__(self, targets: list[Target] | None = None) -> None:
        self._targets = targets or []

    async def get_targets(self) -> list[Target]:
        return self._targets


class MockWriter:
    def __init__(self) -> None:
        self.written: list = []

    async def write_batch(self, metrics: list) -> None:
        self.written.extend(metrics)


class TestValidateConfig:
    def test_valid_config(self) -> None:
        cfg = ICMPConfig(count=3, timeout=timedelta(seconds=5), max_concurrency=10)
        validate_config(cfg)

    def test_zero_count_raises(self) -> None:
        cfg = ICMPConfig(count=0)
        with pytest.raises(InvalidConfigError, match="count"):
            validate_config(cfg)

    def test_negative_count_raises(self) -> None:
        cfg = ICMPConfig(count=-1)
        with pytest.raises(InvalidConfigError, match="count"):
            validate_config(cfg)

    def test_zero_timeout_raises(self) -> None:
        cfg = ICMPConfig(timeout=timedelta(0))
        with pytest.raises(InvalidConfigError, match="timeout"):
            validate_config(cfg)

    def test_zero_max_concurrency_raises(self) -> None:
        cfg = ICMPConfig(max_concurrency=0)
        with pytest.raises(InvalidConfigError, match="max_concurrency"):
            validate_config(cfg)


class TestCollectorName:
    def test_name_returns_icmp(self) -> None:
        import structlog

        logger = structlog.get_logger()
        provider = MockTargetProvider()
        writer = MockWriter()
        c = Collector(logger=logger, cfg=ICMPConfig(), target_provider=provider, writer=writer)
        assert c.name() == "icmp"


class TestCollectorCollect:
    async def test_collect_no_targets(self) -> None:
        import structlog

        logger = structlog.get_logger()
        provider = MockTargetProvider(targets=[])
        writer = MockWriter()
        c = Collector(logger=logger, cfg=ICMPConfig(), target_provider=provider, writer=writer)
        await c.collect()
        assert writer.written == []

    @patch("ixforge_collector.collector.icmp.collector.run_fping")
    async def test_collect_with_targets(self, mock_fping: AsyncMock) -> None:
        import structlog

        mock_fping.return_value = {
            "10.0.0.1": FpingResult(rtts=[1.0, 2.0, 3.0], packets_sent=3),
        }

        logger = structlog.get_logger()
        targets = [_make_target(ip="10.0.0.1")]
        provider = MockTargetProvider(targets=targets)
        writer = MockWriter()
        cfg = ICMPConfig(count=3, timeout=timedelta(seconds=5))
        c = Collector(logger=logger, cfg=cfg, target_provider=provider, writer=writer)
        await c.collect()
        assert len(writer.written) > 0

        names = {m.name for m in writer.written}
        assert "ixforge_icmp_packets_sent" in names
        assert "ixforge_icmp_packets_received" in names
        assert "ixforge_icmp_packet_loss_ratio" in names

    @patch("ixforge_collector.collector.icmp.collector.run_fping")
    async def test_collect_fping_error_produces_loss_metrics(self, mock_fping: AsyncMock) -> None:
        import structlog

        mock_fping.side_effect = RuntimeError("fping failed")

        logger = structlog.get_logger()
        targets = [_make_target(ip="10.0.0.1")]
        provider = MockTargetProvider(targets=targets)
        writer = MockWriter()
        cfg = ICMPConfig(count=3, timeout=timedelta(seconds=5))
        c = Collector(logger=logger, cfg=cfg, target_provider=provider, writer=writer)
        await c.collect()

        # Cuando fping falla, se generan metricas con 0 packets_recv
        assert len(writer.written) > 0
        metric_map = {m.name: m.value for m in writer.written}
        assert metric_map["ixforge_icmp_packets_sent"] == 3.0
        assert metric_map["ixforge_icmp_packets_received"] == 0.0
        assert metric_map["ixforge_icmp_packet_loss_ratio"] == 1.0

    @patch("ixforge_collector.collector.icmp.collector.run_fping")
    async def test_collect_ipv4_and_ipv6_targets(self, mock_fping: AsyncMock) -> None:
        import structlog

        async def side_effect(ips, count, timeout):
            results = {}
            for ip in ips:
                results[str(ip)] = FpingResult(rtts=[1.0, 2.0], packets_sent=2)
            return results

        mock_fping.side_effect = side_effect

        logger = structlog.get_logger()
        targets = [
            _make_target(ip="10.0.0.1", member_id="uuid-m1", member_name="Member A"),
            _make_target(ip="2001:db8::1", member_id="uuid-m2", member_name="Member B"),
        ]
        provider = MockTargetProvider(targets=targets)
        writer = MockWriter()
        cfg = ICMPConfig(count=2, timeout=timedelta(seconds=5))
        c = Collector(logger=logger, cfg=cfg, target_provider=provider, writer=writer)
        await c.collect()

        # Ambos targets deben generar metricas
        ips_in_metrics = {m.labels["ip"] for m in writer.written}
        assert "10.0.0.1" in ips_in_metrics
        assert "2001:db8::1" in ips_in_metrics


class TestCollectorReconfigure:
    async def test_reconfigure_valid(self) -> None:
        import structlog

        logger = structlog.get_logger()
        provider = MockTargetProvider()
        writer = MockWriter()
        c = Collector(logger=logger, cfg=ICMPConfig(), target_provider=provider, writer=writer)
        new_cfg = ICMPConfig(count=5, timeout=timedelta(seconds=10), max_concurrency=20)
        await c.reconfigure(new_cfg)
        assert c._cfg.count == 5

    async def test_reconfigure_invalid_type_raises(self) -> None:
        import structlog

        logger = structlog.get_logger()
        provider = MockTargetProvider()
        writer = MockWriter()
        c = Collector(logger=logger, cfg=ICMPConfig(), target_provider=provider, writer=writer)
        with pytest.raises(TypeError):
            await c.reconfigure("invalid")

    async def test_reconfigure_invalid_config_raises(self) -> None:
        import structlog

        logger = structlog.get_logger()
        provider = MockTargetProvider()
        writer = MockWriter()
        c = Collector(logger=logger, cfg=ICMPConfig(), target_provider=provider, writer=writer)
        with pytest.raises(InvalidConfigError):
            await c.reconfigure(ICMPConfig(count=0))
