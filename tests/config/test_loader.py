import os
from pathlib import Path

import pytest
import yaml

from ixforge_collector.config.loader import load_from_file


class TestLoadFromFile:
    def test_valid_config(self, config_testdata: Path) -> None:
        cfg, missing = load_from_file(config_testdata / "valid.yaml")
        assert cfg.core.url == "http://localhost:8000"
        assert cfg.core.api_key == "test-key-123"
        assert cfg.victoriametrics.url == "http://localhost:8428/api/v1/import/prometheus"
        assert missing == []

    def test_env_var_substitution(self, config_testdata: Path) -> None:
        os.environ["LOG_LEVEL"] = "debug"
        os.environ["CORE_URL"] = "http://core.example.com"
        os.environ["CORE_API_KEY"] = "secret-api-key"
        os.environ["VM_URL"] = "http://vm:8428/api/v1/import/prometheus"
        try:
            cfg, missing = load_from_file(config_testdata / "with_env_vars.yaml")
            assert cfg.core.url == "http://core.example.com"
            assert cfg.core.api_key == "secret-api-key"
            assert cfg.victoriametrics.url == "http://vm:8428/api/v1/import/prometheus"
            assert missing == []
        finally:
            for var in ["LOG_LEVEL", "CORE_URL", "CORE_API_KEY", "VM_URL"]:
                os.environ.pop(var, None)

    def test_missing_env_vars(self, config_testdata: Path) -> None:
        for var in ["LOG_LEVEL", "CORE_URL", "CORE_API_KEY", "VM_URL"]:
            os.environ.pop(var, None)

        _, missing = load_from_file(config_testdata / "with_env_vars.yaml")
        assert len(missing) > 0

    def test_invalid_yaml(self, config_testdata: Path) -> None:
        with pytest.raises(yaml.YAMLError):
            load_from_file(config_testdata / "invalid_yaml.yaml")

    def test_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_from_file("/nonexistent/path.yaml")

    def test_defaults_applied(self, config_testdata: Path) -> None:
        cfg, _ = load_from_file(config_testdata / "valid.yaml")
        assert cfg.log_level == "info"
        assert cfg.http.address == "127.0.0.1:9200"
