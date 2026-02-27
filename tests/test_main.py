from __future__ import annotations

from unittest.mock import patch

import pytest


class TestAsyncRun:
    async def test_invalid_config_file(self) -> None:
        from ixforge_collector.main import _async_run

        with (
            patch("sys.argv", ["ixforge-collector", "--config", "/nonexistent/path.yaml"]),
            pytest.raises(RuntimeError, match="loading config"),
        ):
            await _async_run()

    async def test_config_validation_error(self, tmp_path) -> None:
        from ixforge_collector.main import _async_run

        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(
            "log_level: info\nvictoriametrics:\n  url: http://localhost:8428/api/v1/import/prometheus\n"
        )

        with (
            patch("sys.argv", ["ixforge-collector", "--config", str(cfg_file)]),
            pytest.raises(RuntimeError, match="validating config"),
        ):
            await _async_run()


class TestRun:
    def test_run_handles_exception(self) -> None:
        with (
            patch("ixforge_collector.main._async_run", side_effect=RuntimeError("test error")),
            pytest.raises(SystemExit) as exc_info,
        ):
            from ixforge_collector.main import run

            run()
        assert exc_info.value.code == 1
