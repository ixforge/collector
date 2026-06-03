import threading
from dataclasses import dataclass
from datetime import datetime

_VALID_COUNTER_BITS = (32, 64)


@dataclass
class CounterState:
    """Almacena el estado previo de un contador para calcular rates"""

    value: int
    timestamp: datetime


class RateCalculator:
    """Calcula rates a partir de contadores SNMP

    Es thread-safe para uso concurrente desde multiples threads.
    La key se construye como: switchName/ifName/metricName
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, CounterState] = {}

    def calculate(
        self,
        switch_name: str,
        if_name: str,
        metric_name: str,
        current_value: int,
        current_time: datetime,
        counter_bits: int = 64,
    ) -> float:
        """Calcula el rate entre el valor actual y el anterior

        counter_bits define el tamano del contador SNMP (32 para Counter32,
        64 para Counter64/HC). Esto determina el modulo usado al detectar
        wrap-around; aplicar el modulo equivocado genera rates enormes
        espurios cuando el contador vuelve a cero

        Retorna -1 si es el primer poll o si el delta de tiempo es invalido
        """
        if counter_bits not in _VALID_COUNTER_BITS:
            raise ValueError(f"counter_bits debe ser 32 o 64, recibido {counter_bits}")

        key = f"{switch_name}/{if_name}/{metric_name}"

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

            delta_value = self._calculate_delta(prev.value, current_value, counter_bits)

            return delta_value / delta_seconds

    def clear_state(self, switch_name: str, if_name: str) -> None:
        """Elimina el estado de una interfaz especifica"""
        prefix = f"{switch_name}/{if_name}/"

        with self._lock:
            keys_to_remove = [k for k in self._state if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._state[key]

    def clear_all(self) -> None:
        """Elimina todo el estado almacenado"""
        with self._lock:
            self._state.clear()

    def _calculate_delta(self, prev: int, current: int, counter_bits: int) -> int:
        """Calcula la diferencia entre dos contadores manejando wrap-around

        El modulo usado debe coincidir con el ancho real del contador SNMP:
        Counter32 wrapea a 2^32, Counter64 a 2^64
        """
        if current >= prev:
            return current - prev

        modulus = 1 << counter_bits
        return (modulus - prev) + current
