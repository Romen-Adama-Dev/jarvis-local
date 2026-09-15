#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="${JARVIS_RUNTIME_DIR:-/run/jarvis}"

# En docker compose, el servicio init deja secretos y modelos en /run/jarvis; lo que esté
# definido en el entorno (.env) tiene prioridad, salvo los valores de ejemplo.
load_runtime() {
  local var="$1" file="$RUNTIME_DIR/$2" current="${!1:-}"
  if [[ ( -z "$current" || "$current" == change-me ) && -s "$file" ]]; then
    export "$var=$(cat "$file")"
  fi
}
if [[ "${1:-api}" != init && -d "$RUNTIME_DIR" ]]; then
  load_runtime POSTGRES_PASSWORD postgres_password
  load_runtime JARVIS_API_INTERNAL_TOKEN jarvis_api_internal_token
  if [[ -s "$RUNTIME_DIR/models.env" ]]; then
    while IFS='=' read -r key value; do
      if [[ -n "$key" && -z "${!key:-}" ]]; then export "$key=$value"; fi
    done <"$RUNTIME_DIR/models.env"
  fi
fi

case "${1:-api}" in
    init)
        exec /app/infra/docker/jarvis-init
        ;;
    api)
        alembic upgrade head
        exec uvicorn apps.api.jarvis_api.main:app \
            --host "${JARVIS_API_HOST:-127.0.0.1}" \
            --port "${JARVIS_API_PORT:-8000}"
        ;;
    worker)
        exec arq apps.worker.jarvis_worker.main.WorkerSettings
        ;;
    *)
        exec "$@"
        ;;
esac
