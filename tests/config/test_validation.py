from datetime import timedelta

import pytest

from ixforge_collector.config.models import (
    Config,
    CoreConfig,
    VictoriaMetricsConfig,
    parse_duration,
)
from ixforge_collector.config.validation import ConfigError, validate


class TestParseDuration:
    def test_seconds(self) -> None:
        assert parse_duration("30s") == timedelta(seconds=30)

    def test_minutes(self) -> None:
        assert parse_duration("5m") == timedelta(minutes=5)

    def test_hours(self) -> None:
        assert parse_duration("1h") == timedelta(hours=1)

    def test_milliseconds(self) -> None:
        assert parse_duration("100ms") == timedelta(milliseconds=100)

    def test_passthrough_timedelta(self) -> None:
        td = timedelta(seconds=42)
        assert parse_duration(td) == td

    def test_numeric(self) -> None:
        assert parse_duration(60) == timedelta(seconds=60)

    def test_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="invalid duration format"):
            parse_duration("abc")

    def test_invalid_unit(self) -> None:
        with pytest.raises(ValueError, match="invalid duration format"):
            parse_duration("30x")


class TestValidateCore:
    def _make_config(self, **overrides: object) -> Config:
        core_defaults = {
            "url": "http://localhost:8000",
            "api_key": "test-key-123",
        }
        core_defaults.update(overrides)
        return Config(
            core=CoreConfig(**core_defaults),  # type: ignore[arg-type]
            victoriametrics=VictoriaMetricsConfig(url="http://localhost:8428/api/v1/import/prometheus"),
        )

    def test_valid(self) -> None:
        cfg = self._make_config()
        validate(cfg)

    def test_missing_url(self) -> None:
        cfg = self._make_config(url="")
        with pytest.raises(ConfigError, match=r"core\.url is required"):
            validate(cfg)

    def test_missing_api_key(self) -> None:
        cfg = self._make_config(api_key="")
        with pytest.raises(ConfigError, match=r"core\.api_key is required"):
            validate(cfg)


class TestValidateVictoriaMetrics:
    def test_missing_url(self) -> None:
        cfg = Config(
            core=CoreConfig(url="http://localhost:8000", api_key="test-key"),
            victoriametrics=VictoriaMetricsConfig(url=""),
        )
        with pytest.raises(ConfigError, match=r"victoriametrics\.url is required"):
            validate(cfg)
