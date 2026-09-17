#!/bin/sh
# Servicio "ollama-pull" de docker compose: descarga los modelos que usa Jarvis si aún no
# están (los elegidos por init según la VRAM o fijados en .env, y el de embeddings de la
# memoria de OpenClaw, que la plantilla fija en embeddinggemma). Idempotente.
#
# Con OLLAMA_PRUNE_UNUSED=true borra además los modelos que no sean ninguno de esos, para
# no acumular decenas de GB al cambiar de modelo o de nivel de VRAM.
set -eu

. /run/jarvis/models.env

# Nombre completo tal como lo lista `ollama list` (sin etiqueta = :latest).
full_name() {
  case "$1" in
    *:*) echo "$1" ;;
    *) echo "$1:latest" ;;
  esac
}

keep=""
for model in "$OLLAMA_PRIMARY_MODEL" "$OLLAMA_POWERFUL_MODEL" embeddinggemma; do
  [ -n "$model" ] || continue
  keep="$keep $(full_name "$model")"
  if ollama show "$model" >/dev/null 2>&1; then
    echo "ya descargado: $model"
  else
    echo "descargando: $model"
    ollama pull "$model"
  fi
done

if [ "${OLLAMA_PRUNE_UNUSED:-false}" = true ]; then
  ollama list | awk 'NR > 1 { print $1 }' | while read -r installed; do
    case " $keep " in
      *" $installed "*) ;;
      *)
        echo "borrando modelo sin usar: $installed"
        ollama rm "$installed"
        ;;
    esac
  done
fi
