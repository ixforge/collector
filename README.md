# IXForge Collector

Daemon de monitoreo SNMP e ICMP para infraestructura IXP. Parte del ecosistema [IXForge](https://github.com/ixforge).

Obtiene targets de monitoreo desde el Core via API REST, pollea switches por SNMP y miembros por ICMP, y pushea metricas a VictoriaMetrics.

## Componentes del ecosistema

- [Core](https://github.com/ixforge/core) — API REST, logica de negocio, base de datos
- [Agent](https://github.com/ixforge/agent) — Daemon Rust que aplica configs BIRD en route servers
- **Collector** (este repo) — Daemon Python que recolecta metricas SNMP/ICMP
- [E2E](https://github.com/ixforge/e2e) — Tests end-to-end del pipeline completo

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `fping` instalado en el sistema

## Quick start

```bash
cd collector
uv sync

# VictoriaMetrics local
docker compose -f docker-compose.dev.yaml up -d

# Configuracion
cp configs/ixforge-collector.example.yaml configs/ixforge-collector.yaml
# Editar con la URL del Core y API key

# Ejecutar
uv run ixforge-collector --config configs/ixforge-collector.yaml
```

El collector necesita una API key del Core con scope `monitoring:read`. Las variables de entorno se pueden usar en el YAML con `${VAR_NAME}`.

## Tests

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/
```

## Docker

```bash
docker build -t ixforge-collector .
docker run -v ./configs:/app/configs ixforge-collector
```

## Metricas

**ICMP** (labels: `member_id`, `member_name`, `ip`, `af`):

`ixforge_icmp_rtt_seconds`, `ixforge_icmp_rtt_min_seconds`, `ixforge_icmp_rtt_max_seconds`, `ixforge_icmp_packet_loss_ratio`, `ixforge_icmp_packets_sent`, `ixforge_icmp_packets_received`

**SNMP** (labels: `switch_id`, `hostname`, `ifname`, `member_id`, `connection_id`, `port_id`):

`ixforge_interface_traffic_in_bps`, `ixforge_interface_traffic_out_bps`, `ixforge_interface_packets_in_pps`, `ixforge_interface_packets_out_pps`, `ixforge_interface_errors_in`, `ixforge_interface_errors_out`, `ixforge_interface_discards_out`, `ixforge_interface_oper_status`

## Licencia

Apache 2.0
