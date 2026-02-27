from datetime import UTC, datetime

from ixforge_collector.http_server.health import ComponentHealth, HealthStatus


class TestComponentHealth:
    def test_defaults(self) -> None:
        ch = ComponentHealth(status="ok")
        assert ch.status == "ok"
        assert ch.message == ""
        assert ch.last_run is None

    def test_with_values(self) -> None:
        now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        ch = ComponentHealth(status="ok", message="all good", last_run=now)
        assert ch.message == "all good"
        assert ch.last_run == now


class TestHealthStatus:
    def test_defaults(self) -> None:
        hs = HealthStatus(status="ok")
        assert hs.uptime == ""
        assert hs.start_time is None
        assert hs.components == {}

    def test_with_components(self) -> None:
        hs = HealthStatus(
            status="ok",
            uptime="1h30m",
            components={
                "core": ComponentHealth(status="ok"),
                "scheduler": ComponentHealth(status="running"),
            },
        )
        assert len(hs.components) == 2
        assert hs.components["core"].status == "ok"

    def test_component_independence(self) -> None:
        hs1 = HealthStatus(status="ok")
        hs2 = HealthStatus(status="ok")
        hs1.components["test"] = ComponentHealth(status="ok")
        assert "test" not in hs2.components
