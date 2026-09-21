#!/bin/sh
# Arranque de Alertmanager: con TELEGRAM_BOT_TOKEN y TELEGRAM_AUTHORIZED_USER_IDS (el
# primero de la lista es el propietario) las alertas llegan por Telegram con el mismo bot
# de Jarvis; sin ellos se quedan en la interfaz (127.0.0.1:9093). Enviar con el bot no
# interfiere con OpenClaw, que solo lee sus actualizaciones.
set -eu

config=/tmp/alertmanager.yml
token="${TELEGRAM_BOT_TOKEN:-}"
chat_id="$(printf '%s' "${TELEGRAM_AUTHORIZED_USER_IDS:-}" | cut -d, -f1 | tr -d ' ')"

if [ -n "$token" ] && [ "$token" != change-me ] && [ "$chat_id" -eq "$chat_id" ] 2>/dev/null; then
  umask 077
  printf '%s' "$token" >/tmp/telegram_bot_token
  cat >"$config" <<YAML
route:
  receiver: telegram
  group_by: [alertname, service]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
receivers:
  - name: telegram
    telegram_configs:
      - bot_token_file: /tmp/telegram_bot_token
        chat_id: $chat_id
        parse_mode: HTML
        message: |-
          {{ if eq .Status "firing" }}🔴 <b>Alerta de Jarvis</b>{{ else }}✅ <b>Resuelto</b>{{ end }}
          {{ range .Alerts }}• <b>{{ .Annotations.summary }}</b>
          {{ .Annotations.description }}
          {{ end }}
YAML
  echo "alertmanager: avisos por Telegram al chat $chat_id"
else
  cat >"$config" <<YAML
route:
  receiver: ninguno
receivers:
  - name: ninguno
YAML
  echo "alertmanager: sin Telegram configurado, las alertas solo se ven en la interfaz"
fi

exec /bin/alertmanager --config.file="$config" "$@"
