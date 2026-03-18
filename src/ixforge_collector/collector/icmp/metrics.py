from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv6Address

from ixforge_collector.metrics.victoria import Metric, copy_labels


@dataclass
class PingResult:
    """Resultado de un ping a un target"""

    ip: IPv4Address | IPv6Address
    asn: int
    member_id: str
    member_name: str
    packets_sent: int = 0
    packets_recv: int = 0
    rtt: timedelta = field(default_factory=timedelta)
    min_rtt: timedelta = field(default_factory=timedelta)
    max_rtt: timedelta = field(default_factory=timedelta)
    timestamp: datetime | None = None
    error: Exception | None = None

    def ip_version(self) -> str:
        """Retorna '4' para IPv4 o '6' para IPv6"""
        if isinstance(self.ip, IPv4Address):
            return "4"
        return "6"

    def packet_loss(self) -> float:
        """Calcula el ratio de paquetes perdidos (0.0 - 1.0)"""
        if self.packets_sent == 0:
            return 1.0
        return 1.0 - self.packets_recv / self.packets_sent

    def to_metrics(self) -> list[Metric]:
        """Convierte el resultado de ping a metricas para VictoriaMetrics"""
        ts = self.timestamp if self.timestamp is not None else datetime.now(UTC)

        labels = {
            "ip": str(self.ip),
            "asn": str(self.asn),
            "member_id": self.member_id,
            "member_name": self.member_name,
            "ip_version": self.ip_version(),
        }

        result = [
            Metric(
                name="ixforge_icmp_packets_sent",
                value=float(self.packets_sent),
                timestamp=ts,
                labels=copy_labels(labels),
            ),
            Metric(
                name="ixforge_icmp_packets_received",
                value=float(self.packets_recv),
                timestamp=ts,
                labels=copy_labels(labels),
            ),
            Metric(
                name="ixforge_icmp_packet_loss_ratio",
                value=self.packet_loss(),
                timestamp=ts,
                labels=copy_labels(labels),
            ),
        ]

        # Solo agregar metricas de RTT si hubo respuesta
        if self.packets_recv > 0:
            result.extend(
                [
                    Metric(
                        name="ixforge_icmp_rtt_seconds",
                        value=self.rtt.total_seconds(),
                        timestamp=ts,
                        labels=copy_labels(labels),
                    ),
                    Metric(
                        name="ixforge_icmp_rtt_min_seconds",
                        value=self.min_rtt.total_seconds(),
                        timestamp=ts,
                        labels=copy_labels(labels),
                    ),
                    Metric(
                        name="ixforge_icmp_rtt_max_seconds",
                        value=self.max_rtt.total_seconds(),
                        timestamp=ts,
                        labels=copy_labels(labels),
                    ),
                ]
            )

        return result
