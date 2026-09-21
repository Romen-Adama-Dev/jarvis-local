# livesync-bridge (perfil livesync, docs/OBSIDIAN.md): el upstream fijado a un commit más
# offline-deletions.patch, que propaga a CouchDB los borrados hechos en el vault mientras
# el puente estaba parado (reinicios, recompilaciones). Sin él esas notas seguían en
# Obsidian del móvil para siempre. Mismo proceso de build que el Dockerfile del upstream.
ARG LIVESYNC_BRIDGE_REF=c3760beaa0851214da4860903445d7f6420ca025

FROM alpine:3.20 AS src
ARG LIVESYNC_BRIDGE_REF
RUN apk add --no-cache git
WORKDIR /src
RUN git init -q . \
    && git remote add origin https://github.com/vrtmrz/livesync-bridge.git \
    && git fetch -q --depth 1 origin "${LIVESYNC_BRIDGE_REF}" \
    && git checkout -q FETCH_HEAD
COPY offline-deletions.patch /tmp/
RUN git apply /tmp/offline-deletions.patch && rm -rf .git

FROM docker.io/denoland/deno:2.6.9
WORKDIR /app
RUN chown deno:deno /app \
    && mkdir -p /deno-dir/location_data && chown deno:deno /deno-dir/location_data
USER deno
COPY --from=src --chown=deno:deno /src/ .
RUN deno install --frozen && deno check main.ts
CMD ["deno", "task", "run"]
