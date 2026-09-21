#!/bin/sh
# Arranque de Prometheus: genera los objetivos de las sondas según COMPOSE_PROFILES y
# delega en el binario de la imagen. Los puertos son los de compose.yml por defecto.
set -eu

dir=/etc/prometheus/targets
mkdir -p "$dir"
has_profile() { case ",${COMPOSE_PROFILES:-}," in *",$1,"*) return 0 ;; esac; return 1; }

# target y nombre del servicio, uno por línea -> JSON de file_sd
to_json() {
  first=1
  printf '['
  while read -r target service; do
    [ -n "$target" ] || continue
    [ "$first" = 1 ] || printf ','
    first=0
    printf '{"targets":["%s"],"labels":{"service":"%s"}}' "$target" "$service"
  done
  printf ']\n'
}

{
  echo "http://127.0.0.1:11434/api/version ollama"
  echo "http://127.0.0.1:18789/ openclaw"
  echo "http://127.0.0.1:${SEARXNG_PORT:-8888}/healthz searxng"
  has_profile livesync && echo "http://127.0.0.1:${COUCHDB_PORT:-5984}/_up couchdb"
  true
} | to_json >"$dir/http.json"

echo "http://127.0.0.1:${JARVIS_API_PORT:-8000}/ready api" | to_json >"$dir/ready.json"

{
  has_profile pm && echo "http://127.0.0.1:${OPENPROJECT_PORT:-8090}/health_checks/default openproject"
  true
} | to_json >"$dir/openproject.json"

{
  echo "127.0.0.1:${POSTGRES_PORT:-5432} postgres"
  echo "127.0.0.1:${REDIS_PORT:-6379} redis"
  echo "127.0.0.1:${QDRANT_PORT:-6333} qdrant"
} | to_json >"$dir/tcp.json"

exec /bin/prometheus "$@"
