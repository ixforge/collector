from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import httpx

from ixforge_collector.config.models import VictoriaMetricsConfig


@dataclass
class Metric:
    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)

    def to_prometheus_format(self) -> str:
        """Convierte la metrica al formato Prometheus"""
        keys = sorted(self.labels.keys())
        label_parts = [f'{k}="{_escape_label(self.labels[k])}"' for k in keys]

        label_str = ""
        if label_parts:
            label_str = "{" + ",".join(label_parts) + "}"

        ts = int(self.timestamp.timestamp() * 1000)
        return f"{self.name}{label_str} {self.value:g} {ts}"


def _escape_label(s: str) -> str:
    """Escapa caracteres especiales en valores de labels segun el formato Prometheus"""
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s


def copy_labels(src: dict[str, str]) -> dict[str, str]:
    """Crea una copia del mapa de labels"""
    return dict(src)


class Writer:
    """Escribe metricas a VictoriaMetrics"""

    def __init__(self, client: httpx.AsyncClient, endpoint: str, username: str, password: str) -> None:
        self._client = client
        self._endpoint = endpoint
        self._username = username
        self._password = password

    async def write_test_point(self) -> None:
        """Escribe un punto de prueba para verificar conectividad"""
        metric = Metric(
            name="ixforge_collector_startup",
            value=1,
            timestamp=datetime.now(),
            labels={"type": "test"},
        )
        await self.write(metric)

    async def write(self, metric: Metric) -> None:
        """Escribe una metrica a VictoriaMetrics"""
        await self.write_batch([metric])

    async def write_batch(self, metrics: list[Metric]) -> None:
        """Escribe un lote de metricas a VictoriaMetrics"""
        if not metrics:
            return

        body = "\n".join(m.to_prometheus_format() for m in metrics)

        auth: httpx.BasicAuth | None = None
        if self._username:
            auth = httpx.BasicAuth(self._username, self._password)

        response = await self._client.post(
            self._endpoint,
            content=body,
            headers={"Content-Type": "text/plain"},
            auth=auth,  # type: ignore[arg-type]
        )

        if response.status_code not in (200, 204):
            raise RuntimeError(f"unexpected status code: {response.status_code}")

    async def close(self) -> None:
        await self._client.aclose()


def new_writer(cfg: VictoriaMetricsConfig) -> Writer:
    """Crea un nuevo writer para VictoriaMetrics"""
    parsed = urlparse(cfg.url)

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"invalid VictoriaMetrics URL: {cfg.url}")

    if not parsed.path or parsed.path == "/":
        raise ValueError(
            "VictoriaMetrics URL must include a path (e.g., /api/v1/import/prometheus or /insert/tenant/prometheus)"
        )

    endpoint = cfg.url.rstrip("/")

    import ssl

    ssl_context = ssl.create_default_context()
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(cfg.timeout.total_seconds(), connect=10.0),
        verify=ssl_context,
    )

    return Writer(
        client=client,
        endpoint=endpoint,
        username=cfg.username,
        password=cfg.password,
    )
