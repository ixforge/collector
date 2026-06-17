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

El collector necesita una API key del Core con scope `monitoring:read`, creada
con `POST /api/v1/users/{id}/api-keys` (la key cruda se devuelve una sola vez).
Las variables de entorno se pueden usar en el YAML con `${VAR_NAME}`; una
variable no definida se reemplaza por string vacio (solo deja un warning, no
aborta). Si VictoriaMetrics requiere BasicAuth, completar
`victoriametrics.username` y `victoriametrics.password` en el YAML.

## Tests

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/
```

## Docker

```bash
docker build -t ixforge-collector .
docker run \
  -p 9200:9200 \
  -e IXFORGE_COLLECTOR_API_KEY=<key> \
  -v ./configs:/app/configs \
  ixforge-collector
```

La imagen solo trae `configs/ixforge-collector.example.yaml`; hay que montar un
`configs/ixforge-collector.yaml` real, que es la ruta que usa el entrypoint por
defecto. Publicar `9200` solo si quieres acceder al `/health` desde fuera del host.

## Health

`GET /health` (por defecto en `127.0.0.1:9200`, configurable con `http.address`)
devuelve JSON con `status`, `uptime`, `start_time` y el estado de cada componente
(`core`, `victoriametrics`, `scheduler`). El `status` global es uno de `starting`,
`ok`, `degraded`, `error` o `stopped`. Responde HTTP 503 cuando `status` es `error`,
200 en cualquier otro caso.

## Metricas

**ICMP** (labels: `ip`, `ip_version`, `asn`, `member_id`, `member_name`):

`ixforge_icmp_rtt_seconds`, `ixforge_icmp_rtt_min_seconds`, `ixforge_icmp_rtt_max_seconds`, `ixforge_icmp_packet_loss_ratio`, `ixforge_icmp_packets_sent`, `ixforge_icmp_packets_received`

Las metricas de RTT solo se emiten cuando hubo al menos una respuesta. Hoy el label
`asn` de ICMP siempre vale `0` (el ASN no viene en el target de miembro del Core;
queda pendiente enriquecerlo).

**SNMP** (labels: `switch_id`, `switch_name`, `ifname`, `port_id`, `member_id`, `asn`):

`ixforge_interface_traffic_in_bps`, `ixforge_interface_traffic_out_bps`, `ixforge_interface_packets_in_pps`, `ixforge_interface_packets_out_pps`, `ixforge_interface_errors_in`, `ixforge_interface_errors_out`, `ixforge_interface_discards_out`, `ixforge_interface_oper_status`

## Licencia

Apache 2.0
