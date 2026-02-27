import os
import re
from pathlib import Path

import yaml

from ixforge_collector.config.models import Config

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_from_file(path: str | Path) -> tuple[Config, list[str]]:
    """Carga la configuracion desde un archivo YAML

    Retorna la config parseada y una lista de variables de entorno no definidas
    """
    file_path = Path(path)
    data = file_path.read_text(encoding="utf-8")

    substituted, missing = _substitute_env_vars(data)

    raw = yaml.safe_load(substituted)
    if raw is None:
        raw = {}

    _strip_none_values(raw)
    config = Config(**raw)
    return config, missing


def _strip_none_values(d: dict[str, object]) -> None:
    """Elimina valores None recursivamente para que Pydantic use los defaults"""
    keys_to_remove = [k for k, v in d.items() if v is None]
    for k in keys_to_remove:
        del d[k]
    for v in d.values():
        if isinstance(v, dict):
            _strip_none_values(v)


def _substitute_env_vars(data: str) -> tuple[str, list[str]]:
    """Reemplaza ${VAR_NAME} con el valor de la variable de entorno

    Retorna los datos procesados y una lista de variables no definidas
    """
    missing: list[str] = []

    def replace_match(match: re.Match[str]) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            missing.append(var_name)
            return ""
        return value

    result = _ENV_VAR_RE.sub(replace_match, data)
    return result, missing
