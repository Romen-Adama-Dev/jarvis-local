#!/usr/bin/env bash
set -euo pipefail

case "${1:-api}" in
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
