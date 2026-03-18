from urllib.parse import urlparse

from ixforge_collector.config.models import Config


class ConfigError(Exception):
    pass


def validate(cfg: Config) -> None:
    """Valida la configuracion y lanza ConfigError si hay errores"""
    _validate_core(cfg)
    _validate_victoriametrics(cfg)


def _validate_url(url: str, field: str) -> None:
    """Valida que una URL tenga scheme http/https y host"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError(f"{field} must use http or https scheme")
    if not parsed.netloc:
        raise ConfigError(f"{field} must include a host")


def _validate_core(cfg: Config) -> None:
    core = cfg.core
    if not core.url:
        raise ConfigError("core.url is required")
    _validate_url(core.url, "core.url")
    if not core.api_key:
        raise ConfigError("core.api_key is required")


def _validate_victoriametrics(cfg: Config) -> None:
    vm = cfg.victoriametrics
    if not vm.url:
        raise ConfigError("victoriametrics.url is required")
    _validate_url(vm.url, "victoriametrics.url")
