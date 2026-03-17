from __future__ import annotations

import httpx

from ixforge_collector.config.models import CoreConfig
from ixforge_collector.core_client.client import CoreClient, _parse_targets


class TestParseTargets:
    def test_parse_full_response(self) -> None:
        data = {
            "switches": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "name": "switch1",
                    "management_ip": "10.0.0.1",
                    "snmp_community": "public",
                },
            ],
            "ports": [
                {
                    "id": "00000000-0000-0000-0000-000000000010",
                    "switch_id": "00000000-0000-0000-0000-000000000001",
                    "name": "GE0/0/1",
                    "speed": 1000,
                    "member_id": "00000000-0000-0000-0000-000000000005",
                },
            ],
            "member_ips": [
                {
                    "member_id": "00000000-0000-0000-0000-000000000005",
                    "member_name": "ISP1",
                    "address": "10.0.0.50",
                    "af": 4,
                },
            ],
        }
        targets = _parse_targets(data)
        assert len(targets.switches) == 1
        assert targets.switches[0].name == "switch1"
        assert len(targets.ports) == 1
        assert targets.ports[0].name == "GE0/0/1"
        assert len(targets.member_ips) == 1
        assert targets.member_ips[0].address == "10.0.0.50"

    def test_parse_empty_response(self) -> None:
        targets = _parse_targets({})
        assert targets.switches == []
        assert targets.ports == []
        assert targets.member_ips == []

    def test_parse_port_without_member(self) -> None:
        data = {
            "ports": [
                {
                    "id": "00000000-0000-0000-0000-000000000010",
                    "switch_id": "00000000-0000-0000-0000-000000000001",
                    "name": "GE0/0/1",
                    "speed": 1000,
                    "member_id": None,
                },
            ],
        }
        targets = _parse_targets(data)
        assert targets.ports[0].member_id is None


class TestCoreClient:
    async def test_fetch_targets(self) -> None:
        response_data = {
            "switches": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "name": "switch1",
                    "management_ip": "10.0.0.1",
                    "snmp_community": "public",
                },
            ],
            "ports": [],
            "member_ips": [],
        }

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if "/api/v1/monitoring/targets" in str(request.url):
                return httpx.Response(200, json=response_data)
            return httpx.Response(404)

        transport = httpx.MockTransport(mock_handler)
        cfg = CoreConfig(url="http://localhost:8000", api_key="test-key")
        client = CoreClient(cfg)
        client._client = httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost:8000",
            headers={"X-API-Key": "test-key"},
        )

        targets = await client.fetch_targets()
        assert len(targets.switches) == 1
        assert targets.switches[0].name == "switch1"

    async def test_health_check_ok(self) -> None:
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            if "/health" in str(request.url):
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(404)

        transport = httpx.MockTransport(mock_handler)
        cfg = CoreConfig(url="http://localhost:8000", api_key="test-key")
        client = CoreClient(cfg)
        client._client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8000")

        assert await client.health_check() is True

    async def test_health_check_failure(self) -> None:
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport = httpx.MockTransport(mock_handler)
        cfg = CoreConfig(url="http://localhost:8000", api_key="test-key")
        client = CoreClient(cfg)
        client._client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8000")

        assert await client.health_check() is False

    async def test_fetch_targets_auth_header(self) -> None:
        captured_headers: list[dict] = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_headers.append(dict(request.headers))
            return httpx.Response(200, json={"switches": [], "ports": [], "member_ips": []})

        transport = httpx.MockTransport(mock_handler)
        cfg = CoreConfig(url="http://localhost:8000", api_key="my-secret-key")
        client = CoreClient(cfg)
        client._client = httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost:8000",
            headers={"X-API-Key": "my-secret-key"},
        )

        await client.fetch_targets()
        assert captured_headers[0]["x-api-key"] == "my-secret-key"
