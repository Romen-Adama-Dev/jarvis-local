#!/bin/sh
# Servicio "tailscale" de docker compose: tailscaled en espacio de usuario y alta del nodo
# en el tailnet. Con TS_AUTHKEY entra solo; sin ella espera sin límite a que se abra el
# enlace de inicio de sesión que aparece en `docker compose logs tailscale` (el
# containerboot de la imagen lo corta a los 60 s y reinicia con un enlace nuevo). El nodo
# queda guardado en /var/lib/tailscale, así que solo hace falta la primera vez.
set -eu

SOCKET=/var/run/tailscale/tailscaled.sock
export HOME=/var/lib/tailscale

tailscaled --tun=userspace-networking --statedir=/var/lib/tailscale --socket="$SOCKET" &
daemon=$!
trap 'kill -TERM "$daemon"; wait "$daemon"' TERM INT

until tailscale --socket="$SOCKET" status --json >/dev/null 2>&1; do sleep 1; done

tailscale --socket="$SOCKET" up --hostname="${TS_HOSTNAME:-jarvis}" \
  ${TS_AUTHKEY:+--auth-key="$TS_AUTHKEY"} --timeout=0 &

# Cuando el nodo está conectado: nombre DNS para otros servicios (Setup URI de LiveSync)
# y, con el perfil livesync, CouchDB publicado en el tailnet por HTTPS.
(
  until tailscale --socket="$SOCKET" status >/dev/null 2>&1; do sleep 5; done
  tailscale --socket="$SOCKET" status --json --peers=false \
    | sed -n 's/^[[:space:]]*"DNSName": "\(.*\)\.",$/\1/p' | head -n 1 >/var/run/tailscale/dnsname
  port="${LIVESYNC_HTTPS_PORT:-8443}"
  case ",${COMPOSE_PROFILES:-}," in
    *,livesync,*)
      tailscale --socket="$SOCKET" serve --bg --yes --https="$port" \
        "http://127.0.0.1:${COUCHDB_PORT:-5984}"
      ;;
    *) tailscale --socket="$SOCKET" serve --yes --https="$port" off >/dev/null 2>&1 || true ;;
  esac
) &

wait "$daemon"
