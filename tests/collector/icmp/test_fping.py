from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address

import pytest

from ixforge_collector.collector.icmp.fping import (
    FpingResult,
    build_fping_command,
    parse_fping_output,
)


class TestParseFpingOutput:
    def test_all_alive(self) -> None:
        output = "10.0.0.1 : 0.50 0.60 0.70\n10.0.0.2 : 1.10 1.20 1.30\n"
        results = parse_fping_output(output)
        assert len(results) == 2

        r1 = results["10.0.0.1"]
        assert r1.packets_sent == 3
        assert r1.packets_recv == 3
        assert r1.rtts == [0.50, 0.60, 0.70]

        r2 = results["10.0.0.2"]
        assert r2.packets_sent == 3
        assert r2.packets_recv == 3

    def test_some_lost(self) -> None:
        output = "10.0.0.1 : 0.50 - 0.70\n"
        results = parse_fping_output(output)
        r = results["10.0.0.1"]
        assert r.packets_sent == 3
        assert r.packets_recv == 2
        assert r.rtts == [0.50, 0.70]

    def test_all_lost(self) -> None:
        output = "10.0.0.1 : - - -\n"
        results = parse_fping_output(output)
        r = results["10.0.0.1"]
        assert r.packets_sent == 3
        assert r.packets_recv == 0
        assert r.rtts == []

    def test_empty_output(self) -> None:
        results = parse_fping_output("")
        assert results == {}

    def test_ipv6_addresses(self) -> None:
        output = "2001:db8::1 : 1.50 2.00 2.50\n"
        results = parse_fping_output(output)
        assert "2001:db8::1" in results
        r = results["2001:db8::1"]
        assert r.packets_sent == 3
        assert r.packets_recv == 3

    def test_whitespace_and_blank_lines(self) -> None:
        output = "\n  \n10.0.0.1 : 1.00 2.00\n\n"
        results = parse_fping_output(output)
        assert len(results) == 1
        assert results["10.0.0.1"].packets_sent == 2


class TestFpingResult:
    def test_avg_rtt(self) -> None:
        r = FpingResult(rtts=[1.0, 2.0, 3.0], packets_sent=3)
        assert r.avg_rtt_ms == 2.0

    def test_min_rtt(self) -> None:
        r = FpingResult(rtts=[1.0, 2.0, 3.0], packets_sent=3)
        assert r.min_rtt_ms == 1.0

    def test_max_rtt(self) -> None:
        r = FpingResult(rtts=[1.0, 2.0, 3.0], packets_sent=3)
        assert r.max_rtt_ms == 3.0

    def test_no_rtts_returns_zero(self) -> None:
        r = FpingResult(rtts=[], packets_sent=3)
        assert r.avg_rtt_ms == 0.0
        assert r.min_rtt_ms == 0.0
        assert r.max_rtt_ms == 0.0

    def test_packets_recv(self) -> None:
        r = FpingResult(rtts=[1.0, 2.0], packets_sent=3)
        assert r.packets_recv == 2


class TestBuildFpingCommand:
    def test_ipv4(self) -> None:
        ips = [IPv4Address("10.0.0.1"), IPv4Address("10.0.0.2")]
        cmd = build_fping_command(ips, count=3, timeout=timedelta(seconds=5))
        assert cmd[0] == "fping"
        assert "-4" in cmd
        assert "-C" in cmd
        assert "3" in cmd
        assert "-q" in cmd
        assert "10.0.0.1" in cmd
        assert "10.0.0.2" in cmd

    def test_ipv6(self) -> None:
        ips = [IPv6Address("2001:db8::1")]
        cmd = build_fping_command(ips, count=5, timeout=timedelta(seconds=2))
        assert "-6" in cmd
        assert "2001:db8::1" in cmd

    def test_mixed_raises(self) -> None:
        ips = [IPv4Address("10.0.0.1"), IPv6Address("2001:db8::1")]
        with pytest.raises(ValueError, match="mixed"):
            build_fping_command(ips, count=3, timeout=timedelta(seconds=5))

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="no IPs"):
            build_fping_command([], count=3, timeout=timedelta(seconds=5))

    def test_timeout_in_ms(self) -> None:
        ips = [IPv4Address("10.0.0.1")]
        cmd = build_fping_command(ips, count=3, timeout=timedelta(milliseconds=500))
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "500"
