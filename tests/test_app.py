from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from ipaddress import IPv4Address
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from ixforge_collector.app import App, _ApiTargetProvider
from ixforge_collector.config.models import (
    Config,
    CoreConfig,
    HTTPConfig,
    ICMPConfig,
    PollingConfig,
    SNMPConfig,
    VictoriaMetricsConfig,
)
from ixforge_collector.core_client.models import MemberIP, MonitoringTargets


def _make_config(**overrides) -> Config:
    defaults = {
        "log_level": "error",
        "http": HTTPConfig(address="127.0.0.1:0"),
        "core": CoreConfig(
            url="http://localhost:8000",
            api_key="test-key",
        ),
        "victoriametrics": VictoriaMetricsConfig(
            url="http://localhost:8428/api/v1/import/prometheus",
        ),
        "polling": PollingConfig(
            icmp=ICMPConfig(enabled=False),
            snmp=SNMPConfig(enabled=False),
        ),
    }
    defaults.update(overrides)
    return Config(**defaults)


def _mock_scheduler(is_running=False, last_run=None):
    scheduler = MagicMock()
    scheduler.is_running.return_value = is_running
    scheduler.get_last_run.return_value = last_run
    scheduler.stop = AsyncMock()
    return scheduler


class TestAppGetHealth:
    def test_initial_status(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        health = app.get_health()
        assert health.status == "starting"
        assert health.components["core"].status == "not_connected"
        assert health.components["victoriametrics"].status == "not_connected"

    def test_uptime_format_hours(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._start_time = datetime.now() - timedelta(hours=1, minutes=30, seconds=5)
        app._set_status("ok")
        health = app.get_health()
        assert health.uptime == "1h30m5s"

    def test_uptime_format_minutes(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._start_time = datetime.now() - timedelta(minutes=5, seconds=10)
        health = app.get_health()
        assert health.uptime == "5m10s"

    def test_uptime_format_seconds(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._start_time = datetime.now() - timedelta(seconds=42)
        health = app.get_health()
        assert health.uptime == "42s"

    def test_uptime_empty_when_not_started(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        health = app.get_health()
        assert health.uptime == ""

    def test_with_core_client_shows_ok(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._core_client = AsyncMock()
        health = app.get_health()
        assert health.components["core"].status == "ok"

    def test_with_vm_writer_shows_ok(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._vm_writer = AsyncMock()
        health = app.get_health()
        assert health.components["victoriametrics"].status == "ok"

    def test_scheduler_running_status(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._scheduler = _mock_scheduler(is_running=True)
        health = app.get_health()
        assert health.components["scheduler"].status == "running"

    def test_scheduler_stopped_status(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._scheduler = _mock_scheduler(is_running=False)
        health = app.get_health()
        assert health.components["scheduler"].status == "stopped"

    def test_collector_waiting_when_no_last_run(self) -> None:
        cfg = _make_config(
            polling=PollingConfig(icmp=ICMPConfig(enabled=True)),
        )
        app = App(cfg)
        app._scheduler = _mock_scheduler(is_running=True, last_run=None)
        health = app.get_health()
        assert health.components["icmp"].status == "waiting"

    def test_collector_ok_with_last_run(self) -> None:
        cfg = _make_config(
            polling=PollingConfig(icmp=ICMPConfig(enabled=True)),
        )
        app = App(cfg)
        last_run = datetime.now()
        app._scheduler = _mock_scheduler(is_running=True, last_run=last_run)
        health = app.get_health()
        assert health.components["icmp"].status == "ok"
        assert health.components["icmp"].last_run == last_run

    def test_disabled_collectors_not_in_health(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._scheduler = _mock_scheduler(is_running=True)
        health = app.get_health()
        assert "icmp" not in health.components
        assert "snmp" not in health.components


class TestAppSetStatus:
    def test_set_status_ok(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._set_status("ok")
        assert app.get_health().status == "ok"

    def test_set_status_error(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._set_status("error")
        assert app.get_health().status == "error"

    def test_set_status_stopped(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._set_status("stopped")
        assert app.get_health().status == "stopped"


class TestAppShutdown:
    async def test_shutdown_without_start(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        await app.shutdown()
        assert app.get_health().status == "stopped"

    async def test_shutdown_calls_all_components(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._server = AsyncMock()
        scheduler = _mock_scheduler()
        app._scheduler = scheduler
        app._vm_writer = AsyncMock()
        app._core_client = AsyncMock()
        await app.shutdown()
        app._server.shutdown.assert_awaited_once()
        scheduler.stop.assert_awaited_once()
        app._vm_writer.close.assert_awaited_once()
        app._core_client.close.assert_awaited_once()
        assert app.get_health().status == "stopped"

    async def test_shutdown_collects_errors(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._server = AsyncMock()
        app._server.shutdown.side_effect = RuntimeError("server error")
        scheduler = _mock_scheduler()
        scheduler.stop.side_effect = RuntimeError("scheduler error")
        app._scheduler = scheduler
        with pytest.raises(ExceptionGroup) as exc_info:
            await app.shutdown()
        assert len(exc_info.value.exceptions) == 2
        assert app.get_health().status == "stopped"

    async def test_shutdown_cancels_poll_task(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        cancelled = False

        async def fake_poll():
            nonlocal cancelled
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                cancelled = True
                raise

        app._poll_task = asyncio.create_task(fake_poll())
        await asyncio.sleep(0)
        await app.shutdown()
        assert cancelled


class TestApiTargetProvider:
    async def test_builds_targets(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._targets = MonitoringTargets(
            member_ips=[
                MemberIP(
                    member_id=UUID("00000000-0000-0000-0000-000000000001"),
                    member_name="ISP1",
                    address="10.0.0.50",
                    af=4,
                ),
            ],
        )
        provider = _ApiTargetProvider(app)
        targets = await provider.get_targets()
        assert len(targets) == 1
        assert targets[0].ip == IPv4Address("10.0.0.50")
        assert targets[0].member_name == "ISP1"

    async def test_skips_invalid_ip(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._targets = MonitoringTargets(
            member_ips=[
                MemberIP(
                    member_id=UUID("00000000-0000-0000-0000-000000000001"),
                    member_name="ISP1",
                    address="invalid-ip",
                    af=4,
                ),
            ],
        )
        provider = _ApiTargetProvider(app)
        targets = await provider.get_targets()
        assert targets == []

    async def test_multiple_targets(self) -> None:
        cfg = _make_config()
        app = App(cfg)
        app._targets = MonitoringTargets(
            member_ips=[
                MemberIP(
                    member_id=UUID("00000000-0000-0000-0000-000000000001"),
                    member_name="ISP1",
                    address="10.0.0.50",
                    af=4,
                ),
                MemberIP(
                    member_id=UUID("00000000-0000-0000-0000-000000000002"),
                    member_name="ISP2",
                    address="10.0.0.51",
                    af=4,
                ),
            ],
        )
        provider = _ApiTargetProvider(app)
        targets = await provider.get_targets()
        assert len(targets) == 2
        ips = {str(t.ip) for t in targets}
        assert ips == {"10.0.0.50", "10.0.0.51"}
