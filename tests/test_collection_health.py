"""Regresiones con scheduler, collectors y writer reales, aislando solo IO externo"""

import asyncio
import json
from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

import httpx
import pytest

from ixforge_collector.app import App
from ixforge_collector.collector.snmp.collector import SNMPResult
from ixforge_collector.collector.snmp.oids import OID_IF_DESCR, OID_IF_HC_IN_OCTETS, OID_IF_NAME
from ixforge_collector.config.models import CoreConfig, ICMPConfig, PollingConfig, SNMPConfig
from ixforge_collector.core_client.client import CoreClient
from ixforge_collector.core_client.models import MemberIP, MonitoringTargets, SwitchTarget
from ixforge_collector.http_server.server import _health_to_dict
from ixforge_collector.metrics.victoria import Writer
from ixforge_collector.scheduler.scheduler import Scheduler
from tests.test_app import _make_config


class ExternalIO:
    def __init__(self):
        self.vm_failure = None
        self.core_failure = False
        self.fping_failure = False
        self.snmp_failure = None
        self.delivered = []
        self.targets = MonitoringTargets()

    async def vm(self, request):
        if self.vm_failure == "timeout":
            raise httpx.ReadTimeout("VM unavailable", request=request)
        if self.vm_failure == "http":
            return httpx.Response(503)
        self.delivered.append(request.content.decode())
        return httpx.Response(204)

    async def core(self, request):
        payload = json.loads(json.dumps(asdict(self.targets), default=str))
        return httpx.Response(503 if self.core_failure else 200, json=payload)

    async def subprocess(self, *command, **kwargs):
        ips = command[command.index("-t") + 2 :]
        failed = self.fping_failure and "-6" in command

        class Process:
            returncode = 2 if failed else 1

            async def communicate(self):
                output = "permission denied" if failed else "".join(f"{ip} : - - -\n" for ip in ips)
                return None, output.encode()

        return Process()

    async def snmp_client(self, cfg, switch):
        io = self

        class Client:
            async def walk(self, oid):
                if switch.name == "switch2" and (
                    (io.snmp_failure == "discovery" and oid in (OID_IF_NAME, OID_IF_DESCR))
                    or (io.snmp_failure == "counter" and oid == OID_IF_HC_IN_OCTETS)
                ):
                    raise TimeoutError("SNMP unavailable")
                value = "eth0" if oid in (OID_IF_NAME, OID_IF_DESCR) else 100
                return [SNMPResult(oid=f"{oid}.1", value=value)]

            async def close(self):
                pass

        return Client()


@pytest.fixture
async def running_app(monkeypatch, request):
    io = ExternalIO()
    initial_failure = getattr(request, "param", None)
    io.fping_failure = initial_failure == "icmp"
    io.snmp_failure = "discovery" if initial_failure == "snmp" else None
    monkeypatch.setattr(asyncio, "create_subprocess_exec", io.subprocess)
    monkeypatch.setattr("ixforge_collector.collector.snmp.client.new_snmp_client", io.snmp_client)
    cfg = _make_config(
        core=CoreConfig(url="http://core.test", api_key="test", targets_interval=timedelta(milliseconds=1)),
        polling=PollingConfig(icmp=ICMPConfig(enabled=True), snmp=SNMPConfig(enabled=True)),
    )
    app = App(cfg)
    app._targets = MonitoringTargets(
        switches=[SwitchTarget(UUID(int=i), f"switch{i}", f"10.0.0.{i}", "public") for i in (1, 2)],
        member_ips=[
            MemberIP(UUID(int=i), "member", ip, af) for i, ip, af in ((1, "10.0.0.10", 4), (2, "2001:db8::10", 6))
        ],
    )
    io.targets = app._targets
    writer = Writer(httpx.AsyncClient(transport=httpx.MockTransport(io.vm)), "http://vm.test/import", "", "")
    app._vm_writer = writer
    core = CoreClient(cfg.core, app._logger)
    await core.close()
    core._client = httpx.AsyncClient(base_url="http://core.test", transport=httpx.MockTransport(io.core))
    app._core_client = core
    scheduler = Scheduler(app._logger)
    app._scheduler = scheduler
    app._register_collectors(app._logger, app._targets, scheduler, writer)
    app._set_status("ok")
    await scheduler.start()

    async def initial_round_done():
        while scheduler.get_last_run("icmp") is None or scheduler.get_last_run("snmp") is None:
            await asyncio.sleep(0)

    try:
        await asyncio.wait_for(initial_round_done(), 1)
        yield app, io
    finally:
        await app.shutdown()


async def run_round(app, name):
    await app._scheduler._tasks[name]._run(app._logger)


async def poll_once(app):
    """Ejecuta el loop real hasta completar un poll, sin depender de sleeps de reloj"""
    core = app._core_client
    original_transport = core._client._transport
    completed = asyncio.Event()

    async def handler(request):
        try:
            return await original_transport.handle_async_request(request)
        finally:
            asyncio.get_running_loop().call_soon(completed.set)

    core._client._transport = httpx.MockTransport(handler)
    task = asyncio.create_task(app._poll_targets_loop())
    try:
        await asyncio.wait_for(completed.wait(), 1)
    finally:
        task.cancel()
        await task
        core._client._transport = original_transport


async def test_snmp_failure_after_success_degrades_and_success_recovers(running_app):
    app, io = running_app
    before = app.get_health().components["snmp"]
    assert before.status == "ok"
    io.snmp_failure = "discovery"
    await run_round(app, "snmp")
    failed = app.get_health()
    assert failed.status == "degraded"
    assert failed.components["snmp"].status == "degraded"
    assert failed.components["icmp"].status == "ok"
    assert failed.components["snmp"].last_success == before.last_run
    assert failed.components["snmp"].last_run >= before.last_run
    io.snmp_failure = None
    await run_round(app, "snmp")
    assert app.get_health().status == "ok"
    assert app.get_health().components["snmp"].status == "ok"


async def test_failed_counter_walk_degrades_without_discarding_other_switch(running_app):
    app, io = running_app
    await run_round(app, "snmp")
    io.delivered.clear()
    io.snmp_failure = "counter"
    await run_round(app, "snmp")
    health = app.get_health()
    assert health.status == "degraded"
    assert health.components["snmp"].status == "degraded"
    assert health.components["victoriametrics"].status == "ok"
    assert len(io.delivered) == 1
    assert 'switch_name="switch1"' in io.delivered[0]
    assert 'switch_name="switch2"' not in io.delivered[0]


async def test_one_fping_family_failure_degrades_without_inventing_packet_loss(running_app):
    app, io = running_app
    io.delivered.clear()
    io.fping_failure = True
    await run_round(app, "icmp")
    assert app.get_health().status == "degraded"
    assert app.get_health().components["icmp"].status == "degraded"
    assert app.get_health().components["snmp"].status == "ok"
    assert not io.delivered
    io.fping_failure = False
    await run_round(app, "icmp")
    assert app.get_health().status == "ok"
    assert "ixforge_icmp_packet_loss_ratio" in io.delivered[-1]
    assert app.get_health().components["icmp"].status == "ok"


@pytest.mark.parametrize("failure", ["http", "timeout"])
async def test_delivery_failure_recovers_only_after_real_write(running_app, failure):
    app, io = running_app
    io.vm_failure = failure
    await run_round(app, "icmp")
    health = app.get_health()
    assert health.status == "degraded"
    assert health.components["icmp"].status == "degraded"
    assert health.components["victoriametrics"].status == "degraded"
    io.vm_failure = None
    await app._vm_writer.write_batch([])
    assert app.get_health().components["victoriametrics"].status == "degraded"
    await run_round(app, "snmp")
    assert app.get_health().components["victoriametrics"].status == "ok"
    assert app.get_health().status == "degraded"
    await run_round(app, "icmp")
    assert app.get_health().status == "ok"


async def test_core_and_collectors_recover_independently(running_app):
    app, io = running_app
    io.core_failure = True
    await poll_once(app)
    assert app.get_health().status == "degraded"
    assert app.get_health().components["core"].status == "degraded"
    await run_round(app, "icmp")
    assert app.get_health().status == "degraded"
    io.fping_failure = True
    await run_round(app, "icmp")
    io.core_failure = False
    await poll_once(app)
    assert app.get_health().components["core"].status == "ok"
    assert app.get_health().status == "degraded"
    io.fping_failure = False
    await run_round(app, "icmp")
    assert app.get_health().status == "ok"


@pytest.mark.parametrize("status", ["error", "stopped"])
async def test_poll_outcomes_preserve_severe_status(running_app, status):
    app, io = running_app
    app._set_status(status)
    io.core_failure = True
    await poll_once(app)
    assert app.get_health().status == status
    io.core_failure = False
    await poll_once(app)
    await run_round(app, "icmp")
    assert app.get_health().status == status


async def test_health_serializes_last_success_separately_from_attempt(running_app):
    app, io = running_app
    io.snmp_failure = "discovery"
    await run_round(app, "snmp")
    body = _health_to_dict(app.get_health())
    assert body["status"] == "degraded"
    assert body["components"]["snmp"]["last_success"]
    assert body["components"]["snmp"]["last_run"]


@pytest.mark.parametrize("running_app", ["icmp", "snmp"], indirect=True)
async def test_first_collection_failure_is_not_healthy(running_app):
    app, io = running_app
    name = "icmp" if io.fping_failure else "snmp"
    health = app.get_health()
    assert health.status == "degraded"
    assert health.components[name].status == "degraded"
    assert health.components[name].last_run is not None
    assert health.components[name].last_success is None
    io.fping_failure = False
    io.snmp_failure = None
    await run_round(app, name)
    assert app.get_health().status == "ok"


@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_ip_family_waits_for_other_family_before_finishing(running_app, monkeypatch, cancelled):
    app, io = running_app
    ipv4_finished = asyncio.Event()
    ipv6_started = asyncio.Event()
    release_ipv6 = asyncio.Event()
    io.delivered.clear()

    async def spawn(*command, **kwargs):
        ipv4 = "-4" in command

        class Process:
            returncode = 2 if ipv4 else 1

            async def communicate(self):
                if ipv4:
                    ipv4_finished.set()
                    if cancelled:
                        raise asyncio.CancelledError
                    return None, b"fping execution failed"
                ipv6_started.set()
                await release_ipv6.wait()
                return None, b"2001:db8::10 : - - -\n"

        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    collector = app._scheduler.collectors()["icmp"]
    task = asyncio.create_task(collector.collect())
    try:
        await asyncio.wait_for(ipv4_finished.wait(), 1)
        await asyncio.wait_for(ipv6_started.wait(), 1)
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "the round must wait for IPv6 after IPv4 fails"
        assert not io.delivered
        release_ipv6.set()
        if cancelled:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(ExceptionGroup, match="ICMP ping failed"):
                await task
        assert not io.delivered
    finally:
        release_ipv6.set()
        await asyncio.gather(task, return_exceptions=True)
