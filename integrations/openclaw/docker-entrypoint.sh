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

# Con el perfil tailscale activo, el gateway publica la interfaz web en el tailnet.
TAILSCALE_MODE=off
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
  -e "s|__WHISPER_CLI__|/usr/local/bin/whisper-cli|g" \
  -e "s/__WHISPER_THREADS__/$(nproc)/g" \
  "$TEMPLATE" >"$CONFIG"
chmod 600 "$CONFIG"

echo "== Workspace del agente =="
# Las reglas de trabajo son las del repo en cada arranque; la identidad y el perfil del
# usuario solo se copian la primera vez (el propio agente los va completando).
cp "$APP_DIR/integrations/openclaw/workspace/AGENTS.md" "$WORKSPACE/AGENTS.md"
for f in SOUL.md IDENTITY.md USER.md HEARTBEAT.md; do
  [[ -f "$WORKSPACE/$f" ]] || cp "$APP_DIR/integrations/openclaw/workspace/$f" "$WORKSPACE/$f"
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

echo "== Gateway OpenClaw en 127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789} (Tailscale: ${TAILSCALE_MODE}) =="
exec openclaw gateway --port "${OPENCLAW_GATEWAY_PORT:-18789}"
