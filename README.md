# IXForge Collector

Daemon de monitoreo SNMP e ICMP para infraestructura IXP. Es parte del ecosistema [IXForge](https://github.com/ixforge).

Obtiene los targets de monitoreo desde el Core vía API REST, consulta los switches por SNMP v2c y a los miembros por ICMP (con `fping`), y envía las métricas a VictoriaMetrics.

## Componentes del ecosistema

- [Core](https://github.com/ixforge/core): API REST, lógica de negocio, base de datos
- [Agent](https://github.com/ixforge/agent): daemon Rust que aplica configs BIRD en los route servers
- **Collector** (este repo): daemon Python que recolecta métricas SNMP/ICMP
- [E2E](https://github.com/ixforge/e2e): tests end-to-end del pipeline completo

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- `fping` instalado en el sistema
- Una instancia de VictoriaMetrics accesible
- Una API key del Core con scope `monitoring:read`

## Inicio rápido

```bash
cd collector
uv sync

# VictoriaMetrics local
docker compose -f docker-compose.dev.yaml up -d

# Configuración
cp configs/ixforge-collector.example.yaml configs/ixforge-collector.yaml
# Editar con la URL del Core y habilitar ICMP y/o SNMP en polling
export IXFORGE_COLLECTOR_API_KEY=<key>

# Ejecutar
uv run ixforge-collector --config configs/ixforge-collector.yaml
```

La API key se crea en el Core con `POST /api/v1/users/{id}/api-keys` y scope
`monitoring:read` (la key cruda se devuelve una sola vez). El ejemplo deja
`polling.icmp.enabled` y `polling.snmp.enabled` en `false`: sin habilitar al
menos uno, el collector arranca pero no recolecta nada.

## Configuración

Archivo YAML; `configs/ixforge-collector.example.yaml` es la referencia. Las
duraciones se escriben como `100ms`, `30s`, `5m` o `1h` (un número solo se
interpreta como segundos).

| Campo | Default | Descripción |
|---|---|---|
| `log_level` | `info` | `debug`, `info`, `warn`/`warning` o `error`; otro valor usa `info`. Los logs salen en JSON por stdout |
| `http.address` | `127.0.0.1:9200` | Dirección del servidor de `/health` |
| `core.url` | obligatorio | URL base del Core, con esquema `http` o `https` |
| `core.api_key` | obligatorio | API key con scope `monitoring:read` |
| `core.targets_interval` | `60s` | Cada cuánto se piden los targets al Core |
| `core.timeout` | `10s` | Timeout de las requests al Core |
| `victoriametrics.url` | obligatorio | Endpoint de importación en formato Prometheus, con path (por ejemplo `/api/v1/import/prometheus`) |
| `victoriametrics.timeout` | `10s` | Timeout de las escrituras |
| `victoriametrics.username`, `victoriametrics.password` | vacíos | BasicAuth, solo si VictoriaMetrics lo requiere |
| `polling.icmp.enabled` | `false` | Habilita el collector ICMP |
| `polling.icmp.interval` | `30s` | Intervalo entre rondas |
| `polling.icmp.count` | `3` | Pings por target en cada ronda (`fping -C`) |
| `polling.icmp.timeout` | `5s` | Timeout de cada ping (`fping -t`) |
| `polling.snmp.enabled` | `false` | Habilita el collector SNMP |
| `polling.snmp.interval` | `60s` | Intervalo entre rondas |
| `polling.snmp.timeout` | `10s` | Timeout de cada request SNMP |
| `polling.snmp.retries` | `2` | Reintentos de cada request SNMP |
| `polling.snmp.max_repetitions` | `25` | `max-repetitions` de los GETBULK |
| `polling.snmp.max_concurrency` | `5` | Switches consultados en paralelo |

Las variables de entorno se pueden usar en el YAML con `${VAR_NAME}`; una
variable no definida se reemplaza por un string vacío con un warning. Eso no
aborta la sustitución, pero si el valor vacío corresponde a un campo obligatorio
(`core.url`, `core.api_key`, `victoriametrics.url`), la validación posterior sí
detiene el arranque.

## Arranque

Al arrancar, el collector verifica el Core con `GET /health` (si no responde o
no devuelve 200, solo registra un warning), pide los targets a
`GET /api/v1/monitoring/targets` y escribe en VictoriaMetrics un punto de prueba.
Si falla la validación de la configuración, la consulta de targets o la
escritura de prueba, el proceso termina con código 1. Después arranca el scheduler, que ejecuta de inmediato una primera
ronda de cada collector habilitado, y por último el servidor HTTP de `/health`.

Cada `core.targets_interval` vuelve a pedir los targets: ICMP usa siempre la
última lista recibida y SNMP se reconfigura en caliente cuando la lista cambia.

## Tests

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

El CI (`.github/workflows/ci.yml`) ejecuta estos mismos chequeos, con `pytest`
midiendo cobertura.

## Docker

El stack completo (collector + VictoriaMetrics) está en `docker-compose.yml`:

```bash
cp configs/ixforge-collector.example.yaml configs/ixforge-collector.yaml
cp configs/vm-scrape.example.yml configs/vm-scrape.yml   # y reemplazar CORE_HOST

echo "IXFORGE_COLLECTOR_API_KEY=<key>" > .env
chmod 600 .env

docker compose up -d --build
```

`vm-scrape.yml` no es opcional: el compose lo monta y, si el archivo no existe,
Docker crea un directorio en su lugar y VictoriaMetrics no arranca. Es el scrape
de `/metrics` del Core (cada 30 s y sin credenciales), que trae las métricas que
el collector no puede ver porque no salen de SNMP ni de ICMP, como el conteo de
prefijos por sesión BGP. `CORE_HOST` tiene que ser alcanzable desde el contenedor
de VictoriaMetrics, o sea la IP del host y no `localhost`.

El `example.yaml` usa `localhost` para ejecutar el collector a mano; **para el
compose hay que ajustar la config a la red de contenedores**: `http.address` en
`0.0.0.0:9200` (si no, el `9200` publicado no llega) y la URL de VictoriaMetrics
en `http://victoriametrics:8428/api/v1/import/prometheus` (el nombre del servicio,
no `localhost`). La URL del Core queda apuntando a donde se ejecute el Core.

VictoriaMetrics queda en `127.0.0.1:8428` (solo localhost) con retención de 90
días, y el collector expone su `/health` en el `9200`. El `docker-compose.dev.yaml`
es otra cosa: solo levanta VictoriaMetrics (en el `8428` de todas las interfaces,
con retención de 30 días) para ejecutar el collector a mano.

El compose usa dos redes: `internal` (v4), donde el collector resuelve
`victoriametrics`, y `egress`, con `enable_ipv6: true`, para el ICMP a los
miembros. Sin IPv6 en la red, el contenedor solo tiene v4 (la bridge por defecto
de Docker es solo v4) y el ping a miembros con dirección IPv6 da 100% de pérdida
aunque el host sí los alcance. Docker aplica masquerade a la ULA del contenedor
hacia la interfaz de peering del host, así que el collector hace ping por v4 y
por v6. VictoriaMetrics queda solo en `internal` a propósito: si estuviera en la
red v6, el collector la resolvería también por v6 y la conexión fallaría. El
`/health` se publica solo en v4 (`0.0.0.0:9200:9200`): el servidor escucha en
`0.0.0.0` (v4), y publicarlo también en v6 haría que un cliente v6 reciba un
reset. Requiere Docker con soporte IPv6 (probado en 29.x).

Para ejecutar solo el contenedor del collector:

```bash
docker build -t ixforge-collector .
docker run \
  -p 9200:9200 \
  -e IXFORGE_COLLECTOR_API_KEY=<key> \
  -v ./configs:/app/configs \
  ixforge-collector
```

El entrypoint usa por defecto `configs/ixforge-collector.yaml`, así que hay que
montar uno real. Igual que con el compose, esa config tiene que escuchar en
`0.0.0.0:9200` para que llegue el puerto publicado y apuntar a un VictoriaMetrics
alcanzable desde el contenedor. Publicar `9200` solo si se necesita acceder al
`/health` desde fuera del host. La imagen copia el directorio `configs/` del
contexto de build y no hay `.dockerignore`: en un checkout limpio solo trae los
ejemplos, pero una config local presente al construir queda dentro de la imagen.

## Despliegue

`./deploy.sh <dev|prod> [--yes]` despliega el commit actual de HEAD en el host
del entorno elegido, definido en `deploy.env` (`DEV_HOST` y `PROD_HOST`; ver
`deploy.env.example`). Aborta si hay cambios que no están en un commit, sube el
código con `git archive` a `/opt/ixforge/collector` (reemplaza `src/` y preserva
el `.env` y la config del servidor, que no están versionados), reconstruye con
`docker compose up -d --build`, espera a que `/health` responda en
`localhost:9200` y verifica que el hash de los `.py` de `src/` en el servidor
coincida con el del commit. Entra como root por SSH, con `ssh.exe` si está
disponible y si no con `ssh` (la variable `SSH` permite elegir otro). Para prod
pide escribir `prod` como confirmación (se omite con `--yes` o `-y`). El flujo
dev -> prod completo está en el repo `core` (`docs/staging.md`).

Para actualizar un IXP en producción entre versiones (los tres repos van en el
mismo tag), seguir la [guía de actualización](https://github.com/ixforge/core/blob/main/docs/migracion.md)
del repo `core`.

## Health

`GET /health` (por defecto en `127.0.0.1:9200`, configurable con `http.address`)
devuelve JSON con `status`, `uptime`, `start_time` y, en `components`, el estado
de cada componente: `core`, `victoriametrics`, `scheduler` y los collectors
`icmp`/`snmp` habilitados. El `status` global es uno de `starting`, `ok`,
`degraded`, `error` o `stopped`. Responde HTTP 503 cuando `status` es `error` y
200 en cualquier otro caso. Como el servidor HTTP es lo último que arranca y lo
primero que se detiene, en la práctica `/health` responde `ok` o `degraded`: un
fallo de arranque termina el proceso antes de que el endpoint exista.

Estados de cada componente:

- `core`: `ok`, o `degraded` si falló la última consulta de targets.
- `victoriametrics`, `icmp` y `snmp`: `waiting` hasta completar su primera
  entrega o ronda, `ok` tras un éxito y `degraded` tras un fallo. Para
  VictoriaMetrics, el punto de prueba del arranque ya cuenta como entrega.
- `scheduler`: `running` o `stopped`.

Un fallo al actualizar targets, recolectar o entregar métricas deja el servicio
en `degraded`. Cada componente se recupera con su propio resultado exitoso; una
consulta exitosa al Core no oculta un fallo de SNMP, ICMP o VictoriaMetrics.
Ningún resultado de consulta, ronda o entrega reemplaza los estados `error` o
`stopped`.

En `victoriametrics`, `icmp` y `snmp`, `last_run` indica el último intento
completado, incluso si falló; `last_success` indica el último éxito y solo se
incluye cuando existe. Un lote vacío no cambia la salud de VictoriaMetrics. Una
ronda sin targets es un éxito sin entrega de métricas; los switches sin
comunidad SNMP se omiten con un warning, pero un switch con comunidad y sin IP
de gestión cuenta como fallo. La salud describe el último resultado completado,
sin aplicar un límite de antigüedad a estos timestamps.

Los fallos parciales de SNMP también degradan la ronda, aunque se entregan las
métricas de los switches que respondieron. Un fallo de ejecución de `fping`
(código de salida distinto de 0 o 1, o resultados incompletos), incluso para una
sola familia IP, degrada ICMP y descarta esa ronda para evitar publicar pérdida
de paquetes inventada. La ronda espera que terminen ambas familias IP antes de
reportar el fallo y permitir la siguiente ejecución. Un target que no responde a
pings es un resultado de monitoreo válido: se publican sus métricas de pérdida y
el collector sigue sano.

## Métricas

**ICMP** (labels: `ip`, `ip_version`, `asn`, `member_id`, `member_name`):

`ixforge_icmp_rtt_seconds`, `ixforge_icmp_rtt_min_seconds`, `ixforge_icmp_rtt_max_seconds`, `ixforge_icmp_packet_loss_ratio`, `ixforge_icmp_packets_sent`, `ixforge_icmp_packets_received`

Las métricas de RTT solo se emiten cuando hubo al menos una respuesta
(`ixforge_icmp_rtt_seconds` es el promedio). Hoy el label `asn` de ICMP siempre
vale `0` (el ASN no viene en el target de miembro del Core; queda pendiente
enriquecerlo).

**SNMP** (labels: `switch_id`, `switch_name`, `ifname`, `port_id`, `member_id`, `asn`):

`ixforge_interface_traffic_in_bps`, `ixforge_interface_traffic_out_bps`, `ixforge_interface_packets_in_pps`, `ixforge_interface_packets_out_pps`, `ixforge_interface_errors_in`, `ixforge_interface_errors_out`, `ixforge_interface_discards_out`, `ixforge_interface_oper_status`

Tráfico, paquetes (unicast), errores y descartes son tasas por segundo
calculadas entre consultas, no contadores absolutos; `oper_status` es el estado
de IF-MIB (1 = up, 2 = down, hasta 7 = lowerLayerDown). Se consultan todas las
interfaces del switch (descubiertas por `ifName`, o por `ifDescr` si falla), y
`port_id` y `member_id` quedan vacíos en las que no corresponden a un puerto del
Core. La primera ronda de cada interfaz solo guarda la base de los contadores,
así que sus métricas aparecen desde la segunda. Igual que en ICMP, el label
`asn` de SNMP hoy siempre vale `0`.

**Arranque**: `ixforge_collector_startup{type="test"}` vale 1 y se escribe una
vez en cada arranque para verificar la conexión con VictoriaMetrics.

## Licencia

Apache 2.0
