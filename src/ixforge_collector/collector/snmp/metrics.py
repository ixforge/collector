from dataclasses import dataclass, field
from datetime import datetime

from ixforge_collector.collector.snmp.oids import OperStatus
from ixforge_collector.metrics.victoria import Metric, copy_labels


@dataclass
class InterfacePollResult:
    """Contiene los valores crudos de un poll SNMP

    Estos son los contadores tal como vienen del switch
    """

    switch_hostname: str
    switch_id: str
    if_index: int
    if_name: str
    port_id: str = ""
    member_id: str = ""
    asn: int = 0
    oper_status: OperStatus = OperStatus.UNKNOWN
    in_octets: int = 0
    out_octets: int = 0
    in_ucast_pkts: int = 0
    out_ucast_pkts: int = 0
    in_errors: int = 0
    out_errors: int = 0
    out_discards: int = 0
    timestamp: datetime | None = None


# Nombres de las metricas generadas
_METRIC_NAMES = [
    "ixforge_interface_traffic_in_bps",
    "ixforge_interface_traffic_out_bps",
    "ixforge_interface_packets_in_pps",
    "ixforge_interface_packets_out_pps",
    "ixforge_interface_errors_in",
    "ixforge_interface_errors_out",
    "ixforge_interface_discards_out",
    "ixforge_interface_oper_status",
]


@dataclass
class InterfaceMetrics:
    """Contiene las metricas calculadas (rates) listas para enviar"""

    switch_hostname: str
    switch_id: str
    if_name: str
    port_id: str = ""
    member_id: str = ""
    asn: int = 0
    oper_status: OperStatus = OperStatus.UNKNOWN
    traffic_in_bps: float = 0.0
    traffic_out_bps: float = 0.0
    packets_in_pps: float = 0.0
    packets_out_pps: float = 0.0
    errors_in: float = 0.0
    errors_out: float = 0.0
    discards_out: float = 0.0
    timestamp: datetime | None = field(default=None)

    def to_metrics(self) -> list[Metric]:
        """Convierte InterfaceMetrics a metricas para VictoriaMetrics"""
        ts = self.timestamp if self.timestamp is not None else datetime.now()

        labels = {
            "hostname": self.switch_hostname,
            "ifname": self.if_name,
            "switch_id": self.switch_id,
            "port_id": self.port_id,
            "member_id": self.member_id,
            "asn": str(self.asn),
        }

        values = [
            self.traffic_in_bps,
            self.traffic_out_bps,
            self.packets_in_pps,
            self.packets_out_pps,
            self.errors_in,
            self.errors_out,
            self.discards_out,
            float(self.oper_status),
        ]

        return [
            Metric(
                name=name,
                value=value,
                timestamp=ts,
                labels=copy_labels(labels),
            )
            for name, value in zip(_METRIC_NAMES, values, strict=True)
        ]
