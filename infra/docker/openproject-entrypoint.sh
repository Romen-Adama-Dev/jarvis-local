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

export SECRET_KEY_BASE="$(secret openproject_secret_key_base)"
export DATABASE_URL="postgres://openproject:$(secret openproject_db_password)@postgres:5432/openproject?pool=20&encoding=unicode&reconnect=true"
export OPENPROJECT_SEED_ADMIN_USER_PASSWORD="$(secret openproject_admin_password)"

internal="127.0.0.1:${OPENPROJECT_PORT:-8090},localhost:${OPENPROJECT_PORT:-8090}"
dnsname="$(cat /var/run/tailscale/dnsname 2>/dev/null || true)"
if [[ -n "$dnsname" ]]; then
  export OPENPROJECT_HOST__NAME="${dnsname}:${OPENPROJECT_HTTPS_PORT:-8445}"
  export OPENPROJECT_HTTPS=true
else
  export OPENPROJECT_HOST__NAME="127.0.0.1:${OPENPROJECT_PORT:-8090}"
  export OPENPROJECT_HTTPS=false
fi
export OPENPROJECT_ADDITIONAL__HOST__NAMES="$internal"

exec ./docker/prod/entrypoint-slim.sh "$@"
