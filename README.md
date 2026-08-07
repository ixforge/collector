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
variable no definida se reemplaza por string vacio con un warning. Ojo: eso no
aborta la sustitucion, pero si el valor vacio corresponde a un campo requerido
(`core.url`, `core.api_key`, la URL de VictoriaMetrics), la validacion posterior
sí corta el arranque. Si VictoriaMetrics requiere BasicAuth, completar
`victoriametrics.username` y `victoriametrics.password` en el YAML.

## Tests

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/
```

## Docker

El stack completo (collector + VictoriaMetrics) esta en `docker-compose.yml`:

```bash
cp configs/ixforge-collector.example.yaml configs/ixforge-collector.yaml

echo "IXFORGE_COLLECTOR_API_KEY=<key>" > .env
chmod 600 .env

docker compose up -d --build
```

El `example.yaml` usa `localhost` para correr el collector a mano; **para el
compose hay que ajustar el config a la red de contenedores**: `http.address` en
`0.0.0.0:9200` (si no, el `9200` publicado no llega) y la URL de VictoriaMetrics
en `http://victoriametrics:8428/api/v1/import/prometheus` (el nombre del servicio,
no `localhost`). La URL del Core queda apuntando a donde corra el Core.

VictoriaMetrics queda en `127.0.0.1:8428` (solo localhost) con retencion de 90
dias, y el collector expone su `/health` en el `9200`. El `docker-compose.dev.yaml`
es otra cosa: solo levanta VictoriaMetrics para correr el collector a mano.

El compose usa dos redes: `internal` (v4) donde el collector resuelve
`victoriametrics`, y `egress` con `enable_ipv6: true` para el ICMP a los
miembros. Sin IPv6 en la red, el container solo tiene v4 (la bridge default de
Docker es v4-only) y el ping a miembros con direccion IPv6 da 100% de perdida
aunque el host si los alcance. Docker masquerada la ULA del container hacia la
interfaz de peering del host, asi que el collector pinguea v4 y v6. VictoriaMetrics
queda solo en `internal` a proposito: si estuviera en la red v6, el collector la
resolveria tambien por v6 y la conexion fallaria. Requiere Docker con soporte
IPv6 (probado en 29.x).

Para correr solo el contenedor del collector:

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

## Deploy

`./deploy.sh <dev|prod>` despliega el commit actual de HEAD al entorno elegido.
Aborta si hay cambios sin commitear, sube el codigo con `git archive` (preservando
el `.env` y la config del servidor), reconstruye y verifica que el hash del codigo
en el servidor coincida con el commit. Para prod pide confirmacion (saltable con
`--yes`). El flujo dev -> prod completo esta en el repo `core` (`docs/staging.md`).

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

Trafico, paquetes, errores y descartes son tasas por segundo calculadas entre
polls, no contadores absolutos; `oper_status` es un estado. Igual que en ICMP, el
label `asn` de SNMP hoy siempre vale `0`.

## Licencia

Apache 2.0
