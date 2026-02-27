from enum import IntEnum

# OIDs de IF-MIB (RFC 2863) para monitoreo de interfaces
# Usamos contadores de 64-bit (HC) donde estan disponibles

# ifDescr - Descripcion de la interfaz (para mapear nombre a index)
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"

# ifOperStatus - Estado operacional de la interfaz
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"

# ifInErrors - Paquetes entrantes con errores
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"

# ifOutErrors - Paquetes salientes con errores
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"

# ifOutDiscards - Paquetes salientes descartados
OID_IF_OUT_DISCARDS = "1.3.6.1.2.1.2.2.1.19"

# ifHCInOctets - Bytes entrantes (64-bit counter)
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"

# ifHCOutOctets - Bytes salientes (64-bit counter)
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"

# ifHCInUcastPkts - Paquetes unicast entrantes (64-bit counter)
OID_IF_HC_IN_UCAST_PKTS = "1.3.6.1.2.1.31.1.1.1.7"

# ifHCOutUcastPkts - Paquetes unicast salientes (64-bit counter)
OID_IF_HC_OUT_UCAST_PKTS = "1.3.6.1.2.1.31.1.1.1.11"

# ifName - Nombre corto de la interfaz (ej: GigabitEthernet0/0/1)
OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"


_OPER_STATUS_LABELS = {
    1: "up",
    2: "down",
    3: "testing",
    4: "unknown",
    5: "dormant",
    6: "notPresent",
    7: "lowerLayerDown",
}


class OperStatus(IntEnum):
    """Estado operacional de una interfaz segun IF-MIB"""

    UP = 1
    DOWN = 2
    TESTING = 3
    UNKNOWN = 4
    DORMANT = 5
    NOT_PRESENT = 6
    LOWER_LAYER_DOWN = 7

    def label(self) -> str:
        """Retorna la representacion en texto del estado"""
        return _OPER_STATUS_LABELS.get(self.value, "unknown")
