from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class ComponentHealth:
    """Estado de salud de un componente"""

    status: str
    message: str = ""
    last_run: datetime | None = None


@dataclass
class HealthStatus:
    """Estado de salud del servicio"""

    status: str
    uptime: str = ""
    start_time: datetime | None = None
    components: dict[str, ComponentHealth] = field(default_factory=dict)


class HealthProvider(Protocol):
    """Contrato para obtener el estado de salud"""

    def get_health(self) -> HealthStatus: ...
