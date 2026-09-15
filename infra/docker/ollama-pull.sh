#!/bin/sh
# Servicio "ollama-pull" de docker compose: descarga los modelos que usa Jarvis si aún no
# están (los elegidos por init según la VRAM o fijados en .env, y el de embeddings de la
# memoria de OpenClaw, que la plantilla fija en embeddinggemma). Idempotente.
set -eu

. /run/jarvis/models.env

for model in "$OLLAMA_PRIMARY_MODEL" "$OLLAMA_POWERFUL_MODEL" embeddinggemma; do
  [ -n "$model" ] || continue
  if ollama show "$model" >/dev/null 2>&1; then
    echo "ya descargado: $model"
  else
    echo "descargando: $model"
    ollama pull "$model"
  fi
done
