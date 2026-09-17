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

wait "$daemon"
