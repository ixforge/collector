from __future__ import annotations

import argparse
import asyncio
import signal
import sys

from ixforge_collector.app import App
from ixforge_collector.config.loader import load_from_file
from ixforge_collector.config.models import Config
from ixforge_collector.config.validation import ConfigError, validate
from ixforge_collector.logging import setup, with_component


def run() -> None:
    """Entry point principal del daemon"""
    try:
        asyncio.run(_async_run())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


async def _async_run() -> None:
    """Funcion async principal"""
    args = _parse_args()

    # Logger temporal para startup
    logger = setup("info")
    log = with_component(logger, "main")

    log.info("loading configuration", path=args.config)

    cfg, missing_vars = _load_config(args.config)

    if missing_vars:
        log.warning("undefined environment variables in config", variables=missing_vars)

    _validate_config(cfg)

    log.info("configuration loaded successfully")

    app = App(cfg)

    try:
        await app.start()
    except Exception as exc:
        raise RuntimeError(f"starting application: {exc}") from exc

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    log.info("received shutdown signal")

    try:
        await asyncio.wait_for(app.shutdown(), timeout=30.0)
    except TimeoutError:
        log.error("shutdown timed out after 30 seconds")

    log.info("goodbye")


def _parse_args() -> argparse.Namespace:
    """Parsea argumentos de linea de comandos"""
    parser = argparse.ArgumentParser(description="ixforge-collector monitoring daemon")
    parser.add_argument(
        "--config",
        default="configs/ixforge-collector.yaml",
        help="path to config file",
    )
    return parser.parse_args()


def _load_config(path: str) -> tuple:
    """Carga configuracion desde archivo"""
    try:
        return load_from_file(path)
    except Exception as exc:
        raise RuntimeError(f"loading config: {exc}") from exc


def _validate_config(cfg: Config) -> None:
    """Valida la configuracion"""
    try:
        validate(cfg)
    except ConfigError as exc:
        raise RuntimeError(f"validating config: {exc}") from exc
