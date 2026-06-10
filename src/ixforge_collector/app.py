from __future__ import annotations

import asyncio
import contextlib
import threading
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import TYPE_CHECKING

import structlog

from ixforge_collector.collector.icmp.collector import Target
from ixforge_collector.config.models import Config, ICMPConfig, SNMPConfig
from ixforge_collector.core_client.models import MonitoringTargets
from ixforge_collector.http_server.health import ComponentHealth, HealthStatus
from ixforge_collector.logging import setup, with_component

if TYPE_CHECKING:
    from ixforge_collector.core_client.client import CoreClient
    from ixforge_collector.http_server.server import Server
    from ixforge_collector.metrics.victoria import Writer
    from ixforge_collector.scheduler.scheduler import Scheduler


class App:
    """Orquestador principal del daemon ixforge-collector"""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._logger = setup(cfg.log_level)
        self._core_client: CoreClient | None = None
        self._vm_writer: Writer | None = None
        self._server: Server | None = None
        self._scheduler: Scheduler | None = None
        self._start_time: datetime | None = None
        self._status = "starting"
        self._lock = threading.Lock()
        self._poll_task: asyncio.Task | None = None
        self._targets: MonitoringTargets = MonitoringTargets()

    async def start(self) -> None:
        """Inicia todos los componentes en orden"""
        self._start_time = datetime.now(UTC)
        log = with_component(self._logger, "app")
        log.info("starting ixforge-collector daemon")

        core_client = await self._connect_core(log)
        self._core_client = core_client

        targets = await self._fetch_initial_targets(log, core_client)
        self._targets = targets

        vm_writer = await self._connect_victoriametrics(log)
        self._vm_writer = vm_writer

        log.info("starting scheduler")
        from ixforge_collector.scheduler.scheduler import Scheduler

        scheduler = Scheduler(self._logger)
        self._scheduler = scheduler
        self._register_collectors(log, targets, scheduler, vm_writer)

        try:
            await scheduler.start()
        except Exception as exc:
            self._set_status("error")
            raise RuntimeError("starting scheduler") from exc
        log.info("scheduler started")

        await self._start_http_server(log)

        self._set_status("ok")
        elapsed = datetime.now(UTC) - self._start_time
        log.info("startup complete", uptime=str(elapsed))

        self._poll_task = asyncio.create_task(self._poll_targets_loop())

    async def _connect_core(self, log: structlog.stdlib.BoundLogger) -> CoreClient:
        """Conecta al Core y verifica la conexion"""
        log.info("connecting to Core API", url=self._cfg.core.url)
        from ixforge_collector.core_client.client import CoreClient

        client = CoreClient(self._cfg.core, self._logger)

        try:
            healthy = await client.health_check()
        except Exception as exc:
            self._set_status("error")
            raise RuntimeError("connecting to Core API") from exc

        if not healthy:
            log.warning("Core API health check returned unhealthy, continuing anyway")

        log.info("Core API connection verified")
        return client

    async def _fetch_initial_targets(
        self,
        log: structlog.stdlib.BoundLogger,
        client: CoreClient,
    ) -> MonitoringTargets:
        """Carga los targets de monitoreo desde el Core"""
        log.info("fetching monitoring targets")
        try:
            targets = await client.fetch_targets()
        except Exception as exc:
            self._set_status("error")
            raise RuntimeError("fetching monitoring targets") from exc
        log.info(
            "loaded monitoring targets",
            switches=len(targets.switches),
            ports=len(targets.ports),
            member_ips=len(targets.member_ips),
        )
        return targets

    async def _connect_victoriametrics(self, log: structlog.stdlib.BoundLogger) -> Writer:
        """Conecta a VictoriaMetrics y verifica la conexion"""
        log.info("connecting to VictoriaMetrics")
        from ixforge_collector.metrics.victoria import new_writer

        try:
            writer = new_writer(self._cfg.victoriametrics)
        except Exception as exc:
            self._set_status("error")
            raise RuntimeError("creating VictoriaMetrics writer") from exc

        try:
            await writer.write_test_point()
        except Exception as exc:
            self._set_status("error")
            raise RuntimeError("writing test point to VictoriaMetrics") from exc
        log.info("VictoriaMetrics connection verified")
        return writer

    async def _start_http_server(self, log: structlog.stdlib.BoundLogger) -> None:
        """Inicia el servidor HTTP"""
        log.info("starting HTTP server", address=self._cfg.http.address)
        from ixforge_collector.http_server.server import Server

        self._server = Server(self._cfg.http.address, self)
        await self._server.start()

        if not await self._server.wait_ready(timeout=5.0):
            log.warning("HTTP server did not become ready within 5 seconds")
        log.info("HTTP server started")

    def _register_collectors(
        self,
        log: structlog.stdlib.BoundLogger,
        targets: MonitoringTargets,
        scheduler: Scheduler,
        writer: Writer,
    ) -> None:
        """Registra los collectors habilitados en el scheduler"""
        polling = self._cfg.polling

        if polling.icmp.enabled:
            self._register_icmp(log, polling.icmp, scheduler, writer)
        else:
            log.info("ICMP collector disabled")

        if polling.snmp.enabled:
            self._register_snmp(log, polling.snmp, targets, scheduler, writer)
        else:
            log.info("SNMP collector disabled")

    def _register_icmp(
        self,
        log: structlog.stdlib.BoundLogger,
        cfg: ICMPConfig,
        scheduler: Scheduler,
        writer: Writer,
    ) -> None:
        """Registra el collector ICMP"""
        log.info("registering ICMP collector")
        from ixforge_collector.collector.icmp.collector import Collector as ICMPCollector

        target_provider = _ApiTargetProvider(self)
        collector = ICMPCollector(
            logger=self._logger,
            cfg=cfg,
            target_provider=target_provider,
            writer=writer,
        )
        scheduler.register(collector, cfg.interval)

    def _register_snmp(
        self,
        log: structlog.stdlib.BoundLogger,
        cfg: SNMPConfig,
        targets: MonitoringTargets,
        scheduler: Scheduler,
        writer: Writer,
    ) -> None:
        """Registra el collector SNMP"""
        log.info("registering SNMP collector")
        from ixforge_collector.collector.snmp.client import new_snmp_client
        from ixforge_collector.collector.snmp.collector import Collector as SNMPCollector

        async def client_factory(sw):
            return await new_snmp_client(cfg, sw)

        collector = SNMPCollector(
            cfg=cfg,
            writer=writer,
            targets=targets,
            client_factory=client_factory,
            logger=self._logger,
        )
        scheduler.register(collector, cfg.interval)

    async def _poll_targets_loop(self) -> None:
        """Background task que cada N segundos pide targets al Core y reconfigura si cambiaron"""
        log = with_component(self._logger, "app")
        interval = self._cfg.core.targets_interval.total_seconds()

        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._poll_targets(log)
                    # Un poll exitoso recupera el estado degraded sin pisar
                    # estados mas severos como error o stopped
                    if self._status == "degraded":
                        self._set_status("ok")
                except Exception:
                    log.exception("failed to poll targets")
                    self._set_status("degraded")
        except asyncio.CancelledError:
            pass

    async def _poll_targets(self, log: structlog.stdlib.BoundLogger) -> None:
        """Pide targets al Core y reconfigura collectors si cambiaron"""
        if self._core_client is None:
            return

        new_targets = await self._core_client.fetch_targets()

        # Comparar si cambiaron
        old = self._targets
        if (
            new_targets.switches == old.switches
            and new_targets.ports == old.ports
            and new_targets.member_ips == old.member_ips
        ):
            return

        log.info(
            "monitoring targets changed, reconfiguring",
            switches=len(new_targets.switches),
            ports=len(new_targets.ports),
            member_ips=len(new_targets.member_ips),
        )

        self._targets = new_targets

        # Reconfigura SNMP con los nuevos targets
        if self._scheduler is not None:
            collectors = self._scheduler.collectors()
            if "snmp" in collectors:
                try:
                    await collectors["snmp"].reconfigure(new_targets)
                except Exception:
                    log.exception("failed to reconfigure SNMP collector")

    async def shutdown(self) -> None:
        """Detiene todos los componentes en orden inverso"""
        log = with_component(self._logger, "app")
        log.info("shutting down")

        errors: list[Exception] = []

        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task

        components = [
            (self._server, "shutdown"),
            (self._scheduler, "stop"),
            (self._vm_writer, "close"),
            (self._core_client, "close"),
        ]

        for component, method in components:
            if component is None:
                continue
            try:
                await getattr(component, method)()
            except Exception as exc:
                errors.append(exc)

        self._set_status("stopped")
        log.info("shutdown complete")

        if errors:
            raise ExceptionGroup("shutdown errors", errors)

    def get_health(self) -> HealthStatus:
        """Retorna el estado de salud actual (implementa HealthProvider)"""
        with self._lock:
            components = self._build_component_health()
            uptime = self._format_uptime()

            return HealthStatus(
                status=self._status,
                uptime=uptime,
                start_time=self._start_time,
                components=components,
            )

    def _build_component_health(self) -> dict[str, ComponentHealth]:
        """Construye el mapa de salud de componentes"""
        components: dict[str, ComponentHealth] = {}

        components["core"] = ComponentHealth(
            status="ok" if self._core_client is not None else "not_connected",
        )
        components["victoriametrics"] = ComponentHealth(
            status="ok" if self._vm_writer is not None else "not_connected",
        )

        if self._scheduler is not None:
            status = "running" if self._scheduler.is_running() else "stopped"
            components["scheduler"] = ComponentHealth(status=status)

            collector_enabled = [
                ("icmp", self._cfg.polling.icmp.enabled),
                ("snmp", self._cfg.polling.snmp.enabled),
            ]

            for name, enabled in collector_enabled:
                if not enabled:
                    continue
                last_run = self._scheduler.get_last_run(name)
                if last_run is not None:
                    components[name] = ComponentHealth(status="ok", last_run=last_run)
                else:
                    components[name] = ComponentHealth(status="waiting")

        return components

    def _format_uptime(self) -> str:
        """Formatea el uptime como string legible"""
        if self._start_time is None:
            return ""

        total_secs = int((datetime.now(UTC) - self._start_time).total_seconds())
        hours, remainder = divmod(total_secs, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}h{minutes}m{seconds}s"
        if minutes:
            return f"{minutes}m{seconds}s"
        return f"{seconds}s"

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status


class _ApiTargetProvider:
    """Provee targets ICMP desde los targets cacheados del Core API"""

    def __init__(self, app: App) -> None:
        self._app = app

    async def get_targets(self) -> list[Target]:
        targets: list[Target] = []

        for member_ip in self._app._targets.member_ips:
            try:
                parsed_ip = ip_address(member_ip.address)
            except ValueError:
                continue

            targets.append(
                Target(
                    ip=parsed_ip,
                    asn=0,  # ASN no esta en MemberIP, se podria enriquecer
                    member_id=str(member_ip.member_id),
                    member_name=member_ip.member_name,
                )
            )

        return targets
