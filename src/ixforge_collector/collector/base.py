from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Collector(Protocol):
    """Contrato comun para todos los collectors

    Cada collector es responsable de recolectar metricas de un tipo especifico
    (ICMP, SNMP, etc.) y enviarlas a VictoriaMetrics
    """

    def name(self) -> str:
        """Retorna el nombre unico del collector"""
        ...

    async def collect(self) -> None:
        """Ejecuta una ronda de recoleccion de metricas"""
        ...

    async def reconfigure(self, config: Any) -> None:
        """Actualiza la configuracion del collector en caliente"""
        ...
