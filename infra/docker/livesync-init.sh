#!/bin/sh
# Servicio "livesync-init" (perfil livesync de docker compose): prepara CouchDB para el
# plugin Self-hosted LiveSync de Obsidian, genera la configuración de livesync-bridge
# (que sincroniza CouchDB con los archivos del vault de Jarvis) y el Setup URI con el que
# se configura Obsidian en el móvil o el portátil. Idempotente. Ver docs/OBSIDIAN.md.
set -eu

RUNTIME=/run/jarvis
# Herramientas oficiales de obsidian-livesync, fijadas a un commit.
LIVESYNC_UTILS="https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/${LIVESYNC_UTILS_REF}/utils"
DATABASE="${LIVESYNC_DATABASE:-jarvis_vault}"
COUCHDB_USER="${COUCHDB_USER:-jarvis}"
COUCHDB_PASSWORD="$(cat "$RUNTIME/couchdb_password")"
PASSPHRASE="$(cat "$RUNTIME/livesync_passphrase")"

echo "== Preparando CouchDB (base de datos $DATABASE) =="
hostname=http://couchdb:5984 username="$COUCHDB_USER" password="$COUCHDB_PASSWORD" \
  database="$DATABASE" \
  deno run --quiet --minimum-dependency-age=0 --allow-env --allow-net \
  "$LIVESYNC_UTILS/couchdb/provision.ts"

echo "== Configuración de livesync-bridge =="
mkdir -p /bridge
cat >/bridge/config.json <<JSON
{
  "peers": [
    {
      "type": "couchdb",
      "name": "couchdb",
      "group": "vault",
      "url": "http://couchdb:5984",
      "database": "$DATABASE",
      "username": "$COUCHDB_USER",
      "password": "$COUCHDB_PASSWORD",
      "passphrase": "$PASSPHRASE",
      "obfuscatePassphrase": "$PASSPHRASE",
      "baseDir": "",
      "useRemoteTweaks": true
    },
    {
      "type": "storage",
      "name": "vault",
      "group": "vault",
      "baseDir": "/state/wiki/main/",
      "scanOfflineChanges": true
    }
  ]
}
JSON
chown "${JARVIS_UID:-1000}:${JARVIS_GID:-1000}" /bridge/config.json /bridge-state
chmod 600 /bridge/config.json

# Carpetas que el puente no debe subir a CouchDB (se tapan con tmpfs en su contenedor):
# existen de antemano para que Docker no las cree como root dentro del vault.
VAULT=/state/wiki/main
mkdir -p "$VAULT/.git" "$VAULT/.openclaw-wiki"
chown "${JARVIS_UID:-1000}:${JARVIS_GID:-1000}" /state/wiki "$VAULT" "$VAULT/.git" "$VAULT/.openclaw-wiki"

echo "== Setup URI para Obsidian =="
url="${LIVESYNC_URL:-}"
if [ -z "$url" ] && [ -s /var/run/tailscale/dnsname ]; then
  url="https://$(cat /var/run/tailscale/dnsname):${LIVESYNC_HTTPS_PORT:-8443}"
fi
if [ -z "$url" ]; then
  echo "AVISO: sin Tailscale conectado ni LIVESYNC_URL no se puede generar el Setup URI;" \
    "vuelve a lanzar 'docker compose up -d livesync-init' cuando lo esté." >&2
  exit 0
fi
out="$(hostname="$url" database="$DATABASE" username="$COUCHDB_USER" \
  password="$COUCHDB_PASSWORD" passphrase="$PASSPHRASE" \
  uri_passphrase="$(cat "$RUNTIME/livesync_uri_passphrase")" \
  deno run --quiet --minimum-dependency-age=0 --allow-env \
  "$LIVESYNC_UTILS/setup/generate_setup_uri.ts")"
printf '%s\n' "$out" | grep '^obsidian://' >"$RUNTIME/livesync_setup_uri"
chmod 644 "$RUNTIME/livesync_setup_uri"
echo "Servidor: $url"
echo "Setup URI y su contraseña: docker compose exec openclaw cat /run/jarvis/livesync_setup_uri /run/jarvis/livesync_uri_passphrase"
