import threading
from dataclasses import dataclass
from datetime import datetime

# Maximo valor de un contador de 64-bit
_MAX_UINT64 = 2**64


@dataclass
class CounterState:
    """Almacena el estado previo de un contador para calcular rates"""

    value: int
    timestamp: datetime


class RateCalculator:
    """Calcula rates a partir de contadores SNMP

    Es thread-safe para uso concurrente desde multiples threads.
    La key se construye como: switchHostname/ifName/metricName
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, CounterState] = {}

    def calculate(
        self,
        switch_hostname: str,
        if_name: str,
        metric_name: str,
        current_value: int,
        current_time: datetime,
    ) -> float:
        """Calcula el rate entre el valor actual y el anterior

        Retorna -1 si es el primer poll o si el delta de tiempo es invalido
        """
        key = f"{switch_hostname}/{if_name}/{metric_name}"

        with self._lock:
            prev = self._state.get(key)

            self._state[key] = CounterState(
                value=current_value,
                timestamp=current_time,
            )

            if prev is None:
                return -1

            delta_seconds = (current_time - prev.timestamp).total_seconds()

            if delta_seconds <= 0:
                return -1

            delta_value = self._calculate_delta(prev.value, current_value)

            return delta_value / delta_seconds

    def clear_state(self, switch_hostname: str, if_name: str) -> None:
        """Elimina el estado de una interfaz especifica"""
        prefix = f"{switch_hostname}/{if_name}/"

        with self._lock:
            keys_to_remove = [k for k in self._state if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._state[key]

    def clear_all(self) -> None:
        """Elimina todo el estado almacenado"""
        with self._lock:
            self._state.clear()

    def _calculate_delta(self, prev: int, current: int) -> int:
        """Calcula la diferencia entre dos contadores

        Maneja correctamente el wrap de contadores de 64-bit
        """
        if current >= prev:
            return current - prev

        # Counter wrap: max_uint64 - prev + current
        return (_MAX_UINT64 - prev) + current
