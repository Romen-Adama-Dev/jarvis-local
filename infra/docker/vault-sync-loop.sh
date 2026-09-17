#!/bin/sh
# Servicio opcional "vault-sync" (perfil "vault" de docker compose): versiona el vault de
# Obsidian de Jarvis en un repo git PRIVADO y lo sincroniza cada VAULT_SYNC_INTERVAL
# segundos con scripts/vault-sync. Ver docs/MEMORY.md.
set -eu

: "${VAULT_GIT_URL:?define VAULT_GIT_URL en .env (URL SSH de un repo git privado)}"
VAULT_DIR="${JARVIS_VAULT_DIR:-/vault}"
export GIT_SSH_COMMAND="ssh -i /run/vault/id_key -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/known_hosts"

git config --global user.name "${VAULT_GIT_NAME:-Jarvis}"
git config --global user.email "${VAULT_GIT_EMAIL:-jarvis@localhost}"
git config --global --add safe.directory "$VAULT_DIR"

# El plugin memory-wiki crea el vault al arrancar el gateway.
until [ -d "$VAULT_DIR" ]; do
  echo "esperando a que OpenClaw cree el vault en $VAULT_DIR..."
  sleep 30
done

cd "$VAULT_DIR"
# livesync-init puede haber creado .git vacía de antemano.
[ -f .git/HEAD ] || git init -q -b main
if [ ! -f .gitignore ]; then
  cat >.gitignore <<'EOF'
# Estado interno del plugin memory-wiki (se regenera en el servidor)
.openclaw-wiki/
# Estado local de la app Obsidian en cada dispositivo
.obsidian/workspace*.json
.obsidian/cache
.trash/
EOF
fi
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$VAULT_GIT_URL"
else
  git remote add origin "$VAULT_GIT_URL"
fi

while true; do
  JARVIS_VAULT_DIR="$VAULT_DIR" sh /scripts/vault-sync || echo "vault-sync falló; se reintenta en el siguiente ciclo" >&2
  sleep "${VAULT_SYNC_INTERVAL:-300}"
done
