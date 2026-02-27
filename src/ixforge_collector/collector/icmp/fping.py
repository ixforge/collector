"""Wrapper para ejecutar fping y parsear su salida"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from ipaddress import IPv4Address, IPv6Address


@dataclass
class FpingResult:
    """Resultado de fping para una IP individual"""

    rtts: list[float] = field(default_factory=list)
    packets_sent: int = 0

    @property
    def packets_recv(self) -> int:
        return len(self.rtts)

    @property
    def avg_rtt_ms(self) -> float:
        if not self.rtts:
            return 0.0
        return sum(self.rtts) / len(self.rtts)

    @property
    def min_rtt_ms(self) -> float:
        if not self.rtts:
            return 0.0
        return min(self.rtts)

    @property
    def max_rtt_ms(self) -> float:
        if not self.rtts:
            return 0.0
        return max(self.rtts)


def parse_fping_output(output: str) -> dict[str, FpingResult]:
    """Parsea la salida stderr de fping -C -q

    Formato: IP : rtt1 rtt2 rtt3
    Donde '-' indica paquete perdido
    """
    results: dict[str, FpingResult] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line or " : " not in line:
            continue

        ip_part, values_part = line.split(" : ", 1)
        ip_str = ip_part.strip()
        tokens = values_part.strip().split()

        rtts: list[float] = []
        lost_marker = "-"
        for token in tokens:
            if token != lost_marker:
                rtts.append(float(token))

        results[ip_str] = FpingResult(
            rtts=rtts,
            packets_sent=len(tokens),
        )

    return results


def build_fping_command(
    ips: list[IPv4Address] | list[IPv6Address],
    count: int,
    timeout: timedelta,
) -> list[str]:
    """Construye el comando fping con los argumentos correctos"""
    if not ips:
        raise ValueError("no IPs provided")

    # Detectar version IP y validar que no esten mezcladas
    has_v4 = any(isinstance(ip, IPv4Address) for ip in ips)
    has_v6 = any(isinstance(ip, IPv6Address) for ip in ips)

    if has_v4 and has_v6:
        raise ValueError("mixed IPv4 and IPv6 addresses")

    version_flag = "-4" if has_v4 else "-6"
    timeout_ms = str(int(timeout.total_seconds() * 1000))

    return [
        "fping",
        version_flag,
        "-C",
        str(count),
        "-q",
        "-B1",
        "-r1",
        "-t",
        timeout_ms,
        *[str(ip) for ip in ips],
    ]


async def run_fping(
    ips: list[IPv4Address] | list[IPv6Address],
    count: int,
    timeout: timedelta,
) -> dict[str, FpingResult]:
    """Ejecuta fping y retorna resultados parseados

    fping escribe resultados a stderr con -q, y retorna exit code 1
    si algun host es inalcanzable (no es un error real).
    Usa create_subprocess_exec para evitar inyeccion de comandos
    """
    cmd = build_fping_command(ips, count, timeout)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await proc.communicate()

    # fping retorna 0 si todos alive, 1 si algunos unreachable, 2 si error
    if proc.returncode is not None and proc.returncode >= 2:
        raise RuntimeError(f"fping failed with exit code {proc.returncode}: {stderr.decode()}")

    return parse_fping_output(stderr.decode())
