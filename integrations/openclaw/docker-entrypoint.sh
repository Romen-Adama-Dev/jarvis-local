#!/usr/bin/env bash
# Arranque del gateway OpenClaw en docker compose. En cada inicio genera openclaw.json
# desde la plantilla del repo y .env (la configuración vive en el repo, no en el volumen
# de estado), prepara el workspace del agente y lanza el gateway en primer plano.
# Equivale a scripts/install-openclaw + scripts/configure-telegram del despliegue en host.
set -euo pipefail

APP_DIR=/app
RUNTIME_DIR="${JARVIS_RUNTIME_DIR:-/run/jarvis}"
STATE_DIR="$HOME/.openclaw"
CONFIG="$STATE_DIR/openclaw.json"
TEMPLATE="$APP_DIR/integrations/openclaw/config/openclaw.template.json"
WORKSPACE="$STATE_DIR/workspace-jarvis"

is_placeholder() { [[ -z "$1" || "$1" == change-me ]]; }
sed_escape() { printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'; }

# Descripción del servidor para las plantillas del workspace (IDENTITY.md, TOOLS.md).
describe_hardware() {
  local cpu ram gpu desc=""
  cpu="$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo 2>/dev/null | head -1)"
  ram="$(awk '/^MemTotal:/ {printf "%.0f GB de RAM", $2 / 1048576}' /proc/meminfo 2>/dev/null)"
  gpu="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1 |
    sed -e 's/,\s*/ /' -e 's/MiB/MB/')"
  for part in "$cpu" "$ram" "$gpu"; do
    [[ -n "$part" ]] || continue
    [[ -z "$desc" ]] && desc="$part" || desc="$desc, $part"
  done
  printf '%s' "${desc:-servidor Linux}"
}

# Las plantillas del workspace no llevan datos personales: el nombre del propietario y las
# características del servidor se sustituyen aquí desde .env y de lo que se detecta.
render_workspace_file() {
  sed -e "s|__OWNER_FULL__|$(sed_escape "$OWNER_FULL_NAME")|g" \
    -e "s|__OWNER__|$(sed_escape "$OWNER_NAME")|g" \
    -e "s|__OWNER_TZ__|$(sed_escape "$OWNER_TZ")|g" \
    -e "s|__SERVER_HW__|$(sed_escape "$SERVER_HW")|g" \
    "$1" >"$2"
}
runtime_value() { if [[ -s "$RUNTIME_DIR/$1" ]]; then cat "$RUNTIME_DIR/$1"; fi; }

# Secretos y modelos generados por el servicio init; lo definido en .env tiene prioridad.
if is_placeholder "${JARVIS_API_INTERNAL_TOKEN:-}"; then
  JARVIS_API_INTERNAL_TOKEN="$(runtime_value jarvis_api_internal_token)"
fi
if is_placeholder "${OPENCLAW_GATEWAY_TOKEN:-}"; then
  OPENCLAW_GATEWAY_TOKEN="$(runtime_value openclaw_gateway_token)"
fi
if [[ -s "$RUNTIME_DIR/models.env" ]]; then
  while IFS='=' read -r key value; do
    if [[ -n "$key" && -z "${!key:-}" ]]; then export "$key=$value"; fi
  done <"$RUNTIME_DIR/models.env"
fi
: "${JARVIS_API_INTERNAL_TOKEN:?falta el token interno de la API (¿se ejecutó el servicio init?)}"
: "${OLLAMA_PRIMARY_MODEL:?falta OLLAMA_PRIMARY_MODEL (¿se ejecutó el servicio init?)}"

mkdir -p "$STATE_DIR/secrets" "$WORKSPACE/memory" "$WORKSPACE/outbox"
chmod 700 "$STATE_DIR/secrets"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_USER_ID="${TELEGRAM_AUTHORIZED_USER_IDS:-}"
TELEGRAM_USER_ID="${TELEGRAM_USER_ID%%,*}"
if is_placeholder "$TELEGRAM_BOT_TOKEN" || is_placeholder "$TELEGRAM_USER_ID"; then
  TELEGRAM_ENABLED=false
  TELEGRAM_USER_ID=0
  echo "AVISO: TELEGRAM_BOT_TOKEN/TELEGRAM_AUTHORIZED_USER_IDS sin rellenar en .env: Telegram" \
    "desactivado. La interfaz web sigue disponible en http://127.0.0.1:18789" >&2
else
  TELEGRAM_ENABLED=true
  printf '%s' "$TELEGRAM_BOT_TOKEN" >"$STATE_DIR/secrets/telegram_bot_token"
  chmod 600 "$STATE_DIR/secrets/telegram_bot_token"
fi

# Con el perfil tailscale activo, el gateway publica la interfaz web en el tailnet. Al
# reiniciar el servidor Docker levanta los contenedores sin respetar depends_on: si
# tailscaled aún no está conectado, se espera (TAILSCALE_WAIT_SECONDS) en vez de arrancar
# sin panel hasta el siguiente reinicio del gateway.
TAILSCALE_MODE=off
case ",${COMPOSE_PROFILES:-}," in
  *,tailscale,*)
    for _ in $(seq "${TAILSCALE_WAIT_SECONDS:-180}"); do
      tailscale status >/dev/null 2>&1 && break
      sleep 1
    done
    ;;
esac
if tailscale status >/dev/null 2>&1; then
  TAILSCALE_MODE=serve
fi

echo "== Generando $CONFIG desde la plantilla =="
sed -e "s/__TELEGRAM_USER_ID__/${TELEGRAM_USER_ID}/g" \
  -e "s/__TELEGRAM_ENABLED__/${TELEGRAM_ENABLED}/g" \
  -e "s/__TAILSCALE_MODE__/${TAILSCALE_MODE}/g" \
  -e "s/__JARVIS_API_INTERNAL_TOKEN__/${JARVIS_API_INTERNAL_TOKEN}/g" \
  -e "s/__OPENCLAW_GATEWAY_TOKEN__/${OPENCLAW_GATEWAY_TOKEN}/g" \
  -e "s|__HOME__|${HOME}|g" \
  -e "s|__REPO_DIR__|${APP_DIR}|g" \
  -e "s|__OLLAMA_PRIMARY_MODEL__|${OLLAMA_PRIMARY_MODEL}|g" \
  -e "s/__OLLAMA_CONTEXT_LENGTH__/${OLLAMA_CONTEXT_LENGTH:-32768}/g" \
  -e "s/__OPENPROJECT_PORT__/${OPENPROJECT_PORT:-8090}/g" \
  -e "s/__OPENPROJECT_HTTPS_PORT__/${OPENPROJECT_HTTPS_PORT:-8445}/g" \
  -e "s/__COMPOSE_PROFILES__/${COMPOSE_PROFILES:-}/g" \
  -e "s/__COUCHDB_PORT__/${COUCHDB_PORT:-5984}/g" \
  -e "s/__LIVESYNC_HTTPS_PORT__/${LIVESYNC_HTTPS_PORT:-8443}/g" \
  -e "s|__WHISPER_CLI__|/usr/local/bin/whisper-cli|g" \
  -e "s/__WHISPER_THREADS__/$(nproc)/g" \
  "$TEMPLATE" >"$CONFIG"
chmod 600 "$CONFIG"

echo "== Workspace del agente =="
OWNER_NAME="${JARVIS_OWNER_NAME:-}"
[[ -n "$OWNER_NAME" ]] || OWNER_NAME="mi usuario"
OWNER_FULL_NAME="${JARVIS_OWNER_FULL_NAME:-}"
[[ -n "$OWNER_FULL_NAME" ]] || OWNER_FULL_NAME="$OWNER_NAME"
OWNER_TZ="${JARVIS_OWNER_TIMEZONE:-${TZ:-${CALENDAR_TIMEZONE:-UTC}}}"
SERVER_HW="$(describe_hardware)"
echo "Propietario: $OWNER_FULL_NAME ($OWNER_TZ) · Servidor: $SERVER_HW"
# Las reglas de trabajo son las del repo en cada arranque; la identidad, el perfil del
# usuario y MEMORY.md (las directivas que le da el propietario) solo se copian la primera
# vez: el propio agente los va completando y un reinicio no pisa lo que haya escrito.
render_workspace_file "$APP_DIR/integrations/openclaw/workspace/AGENTS.md" "$WORKSPACE/AGENTS.md"
for f in SOUL.md IDENTITY.md USER.md TOOLS.md HEARTBEAT.md MEMORY.md; do
  [[ -f "$WORKSPACE/$f" ]] ||
    render_workspace_file "$APP_DIR/integrations/openclaw/workspace/$f" "$WORKSPACE/$f"
done
mkdir -p "$STATE_DIR/hooks/nueva-sesion-ayuda"
cp "$APP_DIR"/integrations/openclaw/hooks/nueva-sesion-ayuda/* "$STATE_DIR/hooks/nueva-sesion-ayuda/"

openclaw doctor --fix --non-interactive >/dev/null 2>&1 || true
openclaw hooks enable nueva-sesion-ayuda >/dev/null 2>&1 || true
if [[ ! -f "$STATE_DIR/.jarvis-exec-policy" ]]; then
  # Comandos fuera de la lista blanca piden aprobación en Telegram (ver AGENTS.md).
  openclaw exec-policy set --host gateway --security allowlist --ask on-miss --ask-fallback deny \
    >/dev/null 2>&1 || true
  for c in /usr/bin/uptime /usr/bin/uname /usr/bin/df /usr/bin/free /usr/bin/date /usr/bin/whoami \
    /usr/bin/ls /usr/bin/du /usr/bin/ps; do
    openclaw approvals allowlist add --agent main "$c" >/dev/null 2>&1 || true
  done
  touch "$STATE_DIR/.jarvis-exec-policy"
fi

# Directorio de servicios en el vault de Obsidian (SERVICIOS.md), sin secretos.
if [[ -d "$STATE_DIR/wiki/main" ]]; then
  (cd "$APP_DIR" && .venv/bin/python -m packages.core.services --vault "$STATE_DIR/wiki/main") \
    || echo "AVISO: no se pudo escribir SERVICIOS.md en el vault" >&2
fi

# El agente puede leer su propio entorno (/proc/self/environ): el gateway no necesita
# ninguno de estos secretos (Telegram y el token del panel ya están en $CONFIG y en
# $STATE_DIR/secrets, el token de la API en la configuración de cada servidor MCP).
unset MAIL_PASSWORD CALDAV_PASSWORD COUCHDB_PASSWORD LIVESYNC_PASSPHRASE LIVESYNC_URI_PASSPHRASE \
  OPENPROJECT_ADMIN_PASSWORD POSTGRES_PASSWORD SEARXNG_SECRET GRAFANA_ADMIN_PASSWORD TS_AUTHKEY \
  TELEGRAM_BOT_TOKEN OPENCLAW_GATEWAY_TOKEN JARVIS_API_INTERNAL_TOKEN

echo "== Gateway OpenClaw en 127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789} (Tailscale: ${TAILSCALE_MODE}) =="
exec openclaw gateway --port "${OPENCLAW_GATEWAY_PORT:-18789}"
