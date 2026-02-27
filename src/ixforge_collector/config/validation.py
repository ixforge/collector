from ixforge_collector.config.models import Config


class ConfigError(Exception):
    pass


def validate(cfg: Config) -> None:
    """Valida la configuracion y lanza ConfigError si hay errores"""
    _validate_core(cfg)
    _validate_victoriametrics(cfg)


def _validate_core(cfg: Config) -> None:
    core = cfg.core
    if not core.url:
        raise ConfigError("core.url is required")
    if not core.api_key:
        raise ConfigError("core.api_key is required")


def _validate_victoriametrics(cfg: Config) -> None:
    vm = cfg.victoriametrics
    if not vm.url:
        raise ConfigError("victoriametrics.url is required")
