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

# publish <perfil> <puerto HTTPS en el tailnet> <puerto local>: publica el servicio si su
# perfil está activo y, si no, retira una publicación anterior en ese puerto.
publish() {
  case ",${COMPOSE_PROFILES:-}," in
    *,"$1",*) tailscale --socket="$SOCKET" serve --bg --yes --https="$2" "http://127.0.0.1:$3" ;;
    *) tailscale --socket="$SOCKET" serve --yes --https="$2" off >/dev/null 2>&1 || true ;;
  esac
}

# Cuando el nodo está conectado: nombre DNS para otros servicios (Setup URI de LiveSync,
# enlaces de OpenProject) y los servicios de los perfiles activos publicados en el tailnet
# por HTTPS: CouchDB (livesync), OpenProject (pm) y los editores de ArtCraft (printcraft,
# vectorcraft).
(
  until tailscale --socket="$SOCKET" status >/dev/null 2>&1; do sleep 5; done
  tailscale --socket="$SOCKET" status --json --peers=false \
    | sed -n 's/^[[:space:]]*"DNSName": "\(.*\)\.",$/\1/p' | head -n 1 >/var/run/tailscale/dnsname
  if [ -d /var/run/tailscale-info ]; then
    cp /var/run/tailscale/dnsname /var/run/tailscale-info/dnsname
    chmod 644 /var/run/tailscale-info/dnsname
  fi
  publish livesync "${LIVESYNC_HTTPS_PORT:-8443}" "${COUCHDB_PORT:-5984}"
  publish pm "${OPENPROJECT_HTTPS_PORT:-8445}" "${OPENPROJECT_PORT:-8090}"
  publish printcraft "${PRINTCRAFT_HTTPS_PORT:-8446}" "${PRINTCRAFT_PORT:-8097}"
  publish vectorcraft "${VECTORCRAFT_HTTPS_PORT:-8447}" "${VECTORCRAFT_PORT:-8098}"
) &

wait "$daemon"
