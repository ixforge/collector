import io
import json

from ixforge_collector.logging import _parse_level, nop, setup, with_component


class TestParseLevel:
    def test_debug(self) -> None:
        import logging

        assert _parse_level("debug") == logging.DEBUG

    def test_info(self) -> None:
        import logging

        assert _parse_level("info") == logging.INFO

    def test_warn(self) -> None:
        import logging

        assert _parse_level("warn") == logging.WARNING

    def test_warning(self) -> None:
        import logging

        assert _parse_level("warning") == logging.WARNING

    def test_error(self) -> None:
        import logging

        assert _parse_level("error") == logging.ERROR

    def test_unknown_defaults_to_info(self) -> None:
        import logging

        assert _parse_level("unknown") == logging.INFO

    def test_case_insensitive(self) -> None:
        import logging

        assert _parse_level("DEBUG") == logging.DEBUG
        assert _parse_level("Info") == logging.INFO


class TestSetup:
    def test_returns_bound_logger(self) -> None:
        output = io.StringIO()
        logger = setup("info", output)
        assert logger is not None

    def test_writes_json(self) -> None:
        output = io.StringIO()
        logger = setup("info", output)
        logger.info("test message")
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["event"] == "test message"
        assert data["level"] == "info"


class TestWithComponent:
    def test_adds_component(self) -> None:
        output = io.StringIO()
        logger = setup("info", output)
        log = with_component(logger, "test")
        log.info("hello")
        line = output.getvalue().strip()
        data = json.loads(line)
        assert data["component"] == "test"


class TestNop:
    def test_nop_logger_does_not_crash(self) -> None:
        logger = nop()
        logger.info("this should be discarded")
