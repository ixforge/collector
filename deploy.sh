#!/usr/bin/env bash
# Deploy de IXForge Collector a un entorno
#
#   ./deploy.sh dev
#   ./deploy.sh prod
#   ./deploy.sh prod --yes    # sin confirmacion interactiva
#
# Despliega el commit actual de HEAD (no el working tree): si hay cambios sin
# commitear, aborta. Preserva el .env y la config real del servidor (no versionados)
set -euo pipefail

# Hosts por entorno. Se definen en deploy.env (gitignored, ver deploy.env.example)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$SCRIPT_DIR/deploy.env" ] && . "$SCRIPT_DIR/deploy.env"
declare -A HOSTS=(
  [dev]="${DEV_HOST:-}"
  [prod]="${PROD_HOST:-}"
)

REMOTE_DIR=/opt/ixforge/collector
HEALTH_URL=http://localhost:9200/health

SSH_BIN="${SSH:-$(command -v ssh.exe 2>/dev/null || command -v ssh)}"
[[ -n "$SSH_BIN" ]] || { echo "no encuentro ssh" >&2; exit 1; }

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  B=$'\e[1m'; D=$'\e[2m'; R=$'\e[31m'; G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; Z=$'\e[0m'
else
  B=; D=; R=; G=; Y=; C=; Z=
fi

TOTAL=4
step() { printf '\n%s[%d/%d]%s %s%s%s\n' "$C" "$1" "$TOTAL" "$Z" "$B" "$2" "$Z"; }
ok()   { printf '      %s✓%s %s\n' "$G" "$Z" "$1"; }
warn() { printf '      %s!%s %s\n' "$Y" "$Z" "$1"; }
die()  { printf '\n%s✗ %s%s\n' "$R" "$1" "$Z" >&2; exit 1; }

TARGET="${1:-}"
ASSUME_YES=0
[[ "${2:-}" == "--yes" || "${2:-}" == "-y" ]] && ASSUME_YES=1

[[ -n "$TARGET" && -n "${HOSTS[$TARGET]:-}" ]] || die "uso: ./deploy.sh <${!HOSTS[*]}> [--yes]"
HOST="${HOSTS[$TARGET]}"
ssh_run() { "$SSH_BIN" -o BatchMode=yes -o ConnectTimeout=15 "root@$HOST" "$@"; }

cd "$(git rev-parse --show-toplevel)"
SHA=$(git rev-parse --short HEAD)
SUBJECT=$(git log -1 --format=%s)
TCOLOR=$C; [[ "$TARGET" == prod ]] && TCOLOR=$Y

printf '%sIXForge Collector%s %s·%s deploy → %s%s%s %s(%s)%s\n' "$B" "$Z" "$D" "$Z" "$TCOLOR" "$TARGET" "$Z" "$D" "$HOST" "$Z"
printf '%scommit %s — %s%s\n' "$D" "$SHA" "$SUBJECT" "$Z"

# 1. Chequeos
step 1 "Chequeos previos"
git diff --quiet && git diff --cached --quiet || die "hay cambios sin commitear — commitea antes de deployar"
ok "working tree limpio (desplegando $SHA)"
ssh_run true 2>/dev/null || die "no llego a root@$HOST (VPN conectada?)"
ok "acceso a $HOST"
if [[ "$TARGET" == prod && "$ASSUME_YES" -eq 0 ]]; then
  printf '      %s! vas a deployar a PRODUCCION. escribi "prod" para confirmar: %s' "$Y" "$Z"
  read -r reply < /dev/tty
  [[ "$reply" == "prod" ]] || die "cancelado"
fi

# 2. Subir el commit (preservando .env y configs/ del servidor)
step 2 "Subiendo el commit"
git archive --format=tar HEAD | gzip | ssh_run "
  set -e
  mkdir -p $REMOTE_DIR
  rm -rf $REMOTE_DIR/src
  tar xzf - -C $REMOTE_DIR
"
ok "codigo de $SHA en $REMOTE_DIR"

# 3. Build y arranque
step 3 "Reconstruyendo y levantando"
ssh_run "cd $REMOTE_DIR && docker compose up -d --build" >/dev/null 2>&1
ok "contenedores arriba"

# 4. Verificacion
step 4 "Verificando"
ssh_run "for i in \$(seq 1 20); do curl -sf -m3 $HEALTH_URL >/dev/null && exit 0; sleep 3; done; exit 1" \
  || die "el health no respondio a tiempo"
STATUS=$(ssh_run "curl -sf -m5 $HEALTH_URL | sed -n 's/^{ *\"status\": *\"\([a-z]*\)\".*/\1/p'" || true)
ok "health OK${STATUS:+ (status: $STATUS)}"
EXPECTED=$(find src -type f -name '*.py' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
REMOTE=$(ssh_run "cd $REMOTE_DIR && find src -type f -name '*.py' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1")
[[ "$EXPECTED" == "$REMOTE" ]] || die "el codigo en $HOST no coincide con el commit $SHA"
ok "hash del codigo en $HOST == commit $SHA"

printf '\n%s✓ collector %s desplegado en %s (%s)%s\n' "$G" "$SHA" "$TARGET" "$HOST" "$Z"
