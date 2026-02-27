import re
from datetime import timedelta
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator

_DURATION_RE = re.compile(r"^(\d+)(ms|s|m|h)$")

_DURATION_UNITS: dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}


def parse_duration(value: Any) -> timedelta:
    """Convierte '30s', '5m', '100ms', '1h' a timedelta"""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, int | float):
        return timedelta(seconds=value)

    s = str(value).strip()
    match = _DURATION_RE.match(s)
    if not match:
        raise ValueError(f"invalid duration format: {value!r} (expected: 30s, 5m, 100ms, 1h)")

    amount = int(match.group(1))
    unit = match.group(2)
    return timedelta(seconds=amount * _DURATION_UNITS[unit])


Duration = Annotated[timedelta, BeforeValidator(parse_duration)]


class HTTPConfig(BaseModel):
    address: str = "127.0.0.1:9200"


class CoreConfig(BaseModel):
    url: str = ""
    api_key: str = ""
    targets_interval: Duration = timedelta(seconds=60)
    timeout: Duration = timedelta(seconds=10)


class VictoriaMetricsConfig(BaseModel):
    url: str = ""
    timeout: Duration = timedelta(seconds=10)
    username: str = ""
    password: str = ""


class ICMPConfig(BaseModel):
    enabled: bool = False
    interval: Duration = timedelta(seconds=30)
    count: int = 3
    timeout: Duration = timedelta(seconds=5)
    max_concurrency: int = 50


class SNMPConfig(BaseModel):
    enabled: bool = False
    interval: Duration = timedelta(seconds=60)
    timeout: Duration = timedelta(seconds=10)
    retries: int = 2
    max_repetitions: int = 25
    max_concurrency: int = 5


class PollingConfig(BaseModel):
    icmp: ICMPConfig = ICMPConfig()
    snmp: SNMPConfig = SNMPConfig()


class Config(BaseModel):
    log_level: str = "info"
    http: HTTPConfig = HTTPConfig()
    core: CoreConfig = CoreConfig()
    victoriametrics: VictoriaMetricsConfig = VictoriaMetricsConfig()
    polling: PollingConfig = PollingConfig()
