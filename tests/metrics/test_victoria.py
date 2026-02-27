from datetime import UTC, datetime

import httpx
import pytest

from ixforge_collector.config.models import VictoriaMetricsConfig
from ixforge_collector.metrics.victoria import Metric, Writer, _escape_label, copy_labels, new_writer


class TestMetric:
    def test_to_prometheus_format_simple(self) -> None:
        m = Metric(
            name="test_metric",
            value=42.5,
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            labels={"host": "switch1"},
        )
        result = m.to_prometheus_format()
        assert result.startswith('test_metric{host="switch1"} 42.5 ')

    def test_to_prometheus_format_no_labels(self) -> None:
        m = Metric(
            name="test_metric",
            value=1,
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        )
        result = m.to_prometheus_format()
        assert result.startswith("test_metric 1 ")

    def test_to_prometheus_format_sorted_labels(self) -> None:
        m = Metric(
            name="test_metric",
            value=1,
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            labels={"z": "last", "a": "first"},
        )
        result = m.to_prometheus_format()
        assert 'a="first",z="last"' in result

    def test_to_prometheus_format_escaped_labels(self) -> None:
        m = Metric(
            name="test_metric",
            value=1,
            timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
            labels={"msg": 'hello "world"\nnewline'},
        )
        result = m.to_prometheus_format()
        assert r"hello \"world\"\nnewline" in result

    def test_to_prometheus_format_timestamp_millis(self) -> None:
        ts = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        m = Metric(name="test", value=1, timestamp=ts)
        result = m.to_prometheus_format()
        expected_ts = str(int(ts.timestamp() * 1000))
        assert result.endswith(expected_ts)


class TestEscapeLabel:
    def test_backslash(self) -> None:
        assert _escape_label("a\\b") == "a\\\\b"

    def test_quote(self) -> None:
        assert _escape_label('a"b') == 'a\\"b'

    def test_newline(self) -> None:
        assert _escape_label("a\nb") == "a\\nb"

    def test_combined(self) -> None:
        assert _escape_label('a\\b"c\nd') == 'a\\\\b\\"c\\nd'


class TestCopyLabels:
    def test_creates_independent_copy(self) -> None:
        original = {"a": "1", "b": "2"}
        copied = copy_labels(original)
        copied["c"] = "3"
        assert "c" not in original

    def test_empty(self) -> None:
        assert copy_labels({}) == {}


class TestNewWriter:
    def test_valid_url(self) -> None:
        cfg = VictoriaMetricsConfig(url="http://localhost:8428/api/v1/import/prometheus")
        writer = new_writer(cfg)
        assert isinstance(writer, Writer)

    def test_invalid_url_no_scheme(self) -> None:
        cfg = VictoriaMetricsConfig(url="localhost:8428")
        with pytest.raises(ValueError, match="invalid VictoriaMetrics URL"):
            new_writer(cfg)

    def test_invalid_url_no_path(self) -> None:
        cfg = VictoriaMetricsConfig(url="http://localhost:8428")
        with pytest.raises(ValueError, match="must include a path"):
            new_writer(cfg)

    def test_invalid_url_root_path(self) -> None:
        cfg = VictoriaMetricsConfig(url="http://localhost:8428/")
        with pytest.raises(ValueError, match="must include a path"):
            new_writer(cfg)


class TestWriter:
    async def test_write_batch_empty(self) -> None:
        writer = Writer(
            client=httpx.AsyncClient(),
            endpoint="http://localhost:8428/api/v1/import/prometheus",
            username="",
            password="",
        )
        await writer.write_batch([])

    async def test_write_batch_sends_request(self) -> None:
        responses = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            responses.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(mock_handler)
        client = httpx.AsyncClient(transport=transport)

        writer = Writer(
            client=client,
            endpoint="http://localhost:8428/api/v1/import/prometheus",
            username="",
            password="",
        )

        metrics = [
            Metric(name="test", value=1, timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)),
            Metric(name="test2", value=2, timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)),
        ]

        await writer.write_batch(metrics)
        assert len(responses) == 1
        assert responses[0].headers["content-type"] == "text/plain"

    async def test_write_batch_with_auth(self) -> None:
        captured_auth: list[str | None] = []

        async def mock_handler(request: httpx.Request) -> httpx.Response:
            captured_auth.append(request.headers.get("authorization"))
            return httpx.Response(204)

        transport = httpx.MockTransport(mock_handler)
        client = httpx.AsyncClient(transport=transport)

        writer = Writer(
            client=client,
            endpoint="http://localhost:8428/api/v1/import/prometheus",
            username="user",
            password="pass",
        )

        await writer.write(Metric(name="test", value=1, timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)))
        assert captured_auth[0] is not None
        assert captured_auth[0].startswith("Basic ")

    async def test_write_batch_error_status(self) -> None:
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        transport = httpx.MockTransport(mock_handler)
        client = httpx.AsyncClient(transport=transport)

        writer = Writer(
            client=client,
            endpoint="http://localhost:8428/api/v1/import/prometheus",
            username="",
            password="",
        )

        with pytest.raises(RuntimeError, match="unexpected status code: 500"):
            await writer.write(Metric(name="test", value=1, timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)))
