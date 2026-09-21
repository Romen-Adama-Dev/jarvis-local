# Imagen del servicio backup: el mismo PostgreSQL que la base de datos (pg_dump y
# pg_restore de la misma versión) más curl para las instantáneas de Qdrant y zstd.
FROM postgres:17.2-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl zstd ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY jarvis-backup /usr/local/bin/jarvis-backup
ENTRYPOINT ["/usr/local/bin/jarvis-backup"]
CMD ["loop"]
