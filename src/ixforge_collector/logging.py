import io
import logging
import sys
from typing import Any

import structlog


def setup(level: str = "info", output: Any = None) -> structlog.stdlib.BoundLogger:
    """Configura structlog con JSON output y retorna el logger raiz"""
    if output is None:
        output = sys.stdout

    log_level = _parse_level(level)

    logging.basicConfig(
        format="%(message)s",
        stream=output,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Configurar el formatter para usar JSON
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )

    for handler in logging.root.handlers:
        handler.setFormatter(formatter)

    # Silenciar loggers ruidosos de terceros
    for noisy in ("httpx", "httpcore", "hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return structlog.get_logger()


def with_component(logger: structlog.stdlib.BoundLogger, component: str) -> structlog.stdlib.BoundLogger:
    """Retorna un logger con el atributo component agregado"""
    return logger.bind(component=component)


def nop() -> structlog.stdlib.BoundLogger:
    """Retorna un logger que descarta toda la salida"""
    nop_logger = logging.getLogger("ixforge_collector.nop")
    nop_logger.handlers = [logging.StreamHandler(io.StringIO())]
    nop_logger.propagate = False
    nop_logger.setLevel(logging.CRITICAL + 1)

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    return structlog.wrap_logger(nop_logger)


def _parse_level(level: str) -> int:
    """Parsea el nivel de log string a constante logging"""
    levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    return levels.get(level.lower(), logging.INFO)
