#!/bin/bash
# Arranque de los contenedores de OpenProject (perfil pm): toma los secretos que genera
# init en /run/jarvis y el nombre del servidor en el tailnet, y delega en el entrypoint de
# la imagen con la orden recibida (web, worker o seeder).
#
# Con Tailscale, OpenProject se publica en https://<nombre>.ts.net:<OPENPROJECT_HTTPS_PORT>
# y ese es su nombre canónico (enlaces, correos). Jarvis sigue hablándole por
# 127.0.0.1:<OPENPROJECT_PORT>, admitido como nombre adicional.
set -euo pipefail

RUNTIME_DIR=/run/jarvis
secret() {
  if [[ ! -s "$RUNTIME_DIR/$1" ]]; then
    echo "falta $RUNTIME_DIR/$1 (¿se ejecutó el servicio init?)" >&2
    exit 1
  fi
  cat "$RUNTIME_DIR/$1"
}

# Asignar antes de exportar: con `export X="$(...)"` un secreto que falta no pararía el arranque.
SECRET_KEY_BASE="$(secret openproject_secret_key_base)"
db_password="$(secret openproject_db_password)"
DATABASE_URL="postgres://openproject:${db_password}@postgres:5432/openproject?pool=20&encoding=unicode&reconnect=true"
OPENPROJECT_SEED_ADMIN_USER_PASSWORD="$(secret openproject_admin_password)"
export SECRET_KEY_BASE DATABASE_URL OPENPROJECT_SEED_ADMIN_USER_PASSWORD

# Lista en formato JSON: separada por comas se toma como un único nombre.
internal="[\"127.0.0.1:${OPENPROJECT_PORT:-8090}\", \"localhost:${OPENPROJECT_PORT:-8090}\"]"
dnsname="$(cat /var/run/tailscale-info/dnsname 2>/dev/null || true)"
if [[ -n "$dnsname" ]]; then
  export OPENPROJECT_HOST__NAME="${dnsname}:${OPENPROJECT_HTTPS_PORT:-8445}"
  export OPENPROJECT_HTTPS=true
else
  export OPENPROJECT_HOST__NAME="127.0.0.1:${OPENPROJECT_PORT:-8090}"
  export OPENPROJECT_HTTPS=false
fi
export OPENPROJECT_ADDITIONAL__HOST__NAMES="$internal"

# Correo: la cuenta IMAP/SMTP de Jarvis (MAIL_*). Sin ella, OpenProject no envía nada.
mail_from="${MAIL_FROM:-${MAIL_USERNAME:-}}"
if [[ "${MAIL_PROVIDER:-imap}" == "imap" && -n "${SMTP_HOST:-}" && -n "${MAIL_USERNAME:-}" ]]; then
  export OPENPROJECT_EMAIL__DELIVERY__METHOD=smtp
  export OPENPROJECT_SMTP__ADDRESS="$SMTP_HOST"
  export OPENPROJECT_SMTP__PORT="${SMTP_PORT:-587}"
  export OPENPROJECT_SMTP__DOMAIN="${mail_from##*@}"
  export OPENPROJECT_SMTP__AUTHENTICATION=plain
  export OPENPROJECT_SMTP__USER__NAME="$MAIL_USERNAME"
  export OPENPROJECT_SMTP__PASSWORD="${MAIL_PASSWORD:-}"
  if [[ "${SMTP_SECURITY:-starttls}" == "ssl" ]]; then
    export OPENPROJECT_SMTP__SSL=true OPENPROJECT_SMTP__ENABLE__STARTTLS__AUTO=false
  else
    export OPENPROJECT_SMTP__SSL=false OPENPROJECT_SMTP__ENABLE__STARTTLS__AUTO=true
  fi
  export OPENPROJECT_MAIL__FROM="$mail_from"
else
  export OPENPROJECT_EMAIL__DELIVERY__METHOD=none
fi
# Correo del admin humano (lo aplica openproject-setup.rb también a una base ya creada).
export JARVIS_ADMIN_MAIL="${OPENPROJECT_ADMIN_MAIL:-$mail_from}"
export OPENPROJECT_SEED_ADMIN_USER_MAIL="${JARVIS_ADMIN_MAIL:-admin@jarvis.invalid}"

exec ./docker/prod/entrypoint-slim.sh "$@"
