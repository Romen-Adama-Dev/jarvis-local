# Copias de seguridad y restauración

Perfil `backup` de `compose.yml`: una copia diaria de todo lo que no se puede volver a
descargar, con la pila en marcha, y scripts para hacer una copia a mano, restaurarla y
probar que se restaura.

```bash
# COMPOSE_PROFILES=...,backup en .env: copia diaria a BACKUP_TIME
scripts/backup                 # una copia ahora
scripts/backup --list          # copias disponibles
scripts/test-restore           # prueba la última copia sin tocar nada (ver abajo)
scripts/restore <copia>        # sustituye los datos actuales por los de la copia
```

## Qué se guarda

Cada copia es una carpeta `BACKUP_PATH/AAAA-MM-DD_HHMM/` (por defecto `./backups`, fuera
de git) con sus sumas en `SHA256SUMS`:

| Fichero | Contenido |
|---|---|
| `postgres/jarvis.dump`, `postgres/openproject.dump` | Bases de datos (`pg_dump -Fc`): documentos, fragmentos, conversaciones; todo OpenProject |
| `postgres/globals.sql` | Roles de PostgreSQL (el de OpenProject, con su contraseña) |
| `qdrant/<colección>.snapshot` | Instantánea de cada colección de Qdrant (vectores del RAG) |
| `runtime.tar.zst` | Secretos que genera `init` (`jarvis_runtime`): sin ellos no se abren las bases de datos ni el vault cifrado de LiveSync |
| `openclaw.tar.zst` | Estado de OpenClaw: workspace, **vault de Obsidian**, sesiones, credenciales de canales, adjuntos recibidos (sin `cache`, `tmp`, `npm`) |
| `srv.tar.zst` | Documentos subidos y datos de la API (sin modelos) |
| `couchdb-data.tar.zst`, `couchdb-config.tar.zst` | CouchDB de LiveSync (Obsidian en el móvil) |
| `openproject-assets.tar.zst` | Adjuntos de OpenProject |
| `env` | El `.env` (permisos 600) |

No se guarda lo que se recupera solo: modelos de Ollama, fastembed y whisper (se
descargan de nuevo), Redis (cola de trabajos), Prometheus y Grafana, y el estado de
Tailscale (restaurarlo en otra máquina duplicaría el nodo; se vuelve a iniciar sesión).

Con los datos de la VM de desarrollo (7 documentos, 770 fragmentos, 3 proyectos de
OpenProject) una copia ocupa ~95 MB y tarda ~15 s. Se guardan las `BACKUP_KEEP` (7) más
recientes.

**Las copias contienen secretos** (`env`, `runtime.tar.zst`, credenciales de OpenClaw).
Las carpetas se crean con permisos 700; si se copian fuera del servidor, cifradas (por
ejemplo `restic` o `age`).

## Configuración (.env)

| Variable | Por defecto | |
|---|---|---|
| `BACKUP_PATH` | `./backups` | Carpeta de destino en el host (mejor en otro disco) |
| `BACKUP_TIME` | `03:30` | Hora de la copia diaria, en `JARVIS_OWNER_TIMEZONE` (o `CALENDAR_TIMEZONE`, o UTC) |
| `BACKUP_KEEP` | `7` | Copias que se conservan |

Las copias quedan a nombre de `JARVIS_UID`:`JARVIS_GID`.

## Restaurar

```bash
scripts/restore 2026-09-21_0330
```

Pide escribir `restaurar`, comprueba las sumas, para la pila, vuelca los volúmenes,
levanta PostgreSQL y Qdrant, restaura las bases de datos (las borra y las crea desde la
copia) y las colecciones, y vuelve a levantar todo. Después, `scripts/check-integrations`.

**En un servidor nuevo**: clona el repo, copia la carpeta de la copia a `./backups` y
ejecuta `scripts/restore <copia>` antes del primer `docker compose up`. Si no hay `.env`,
se usa el de la copia; si lo hay, el de la copia se deja en `.env.restaurado`. Con
`OPENCLAW_STATE_PATH` en `.env`, el estado de OpenClaw se restaura en ese directorio.

## Probar una copia

```bash
scripts/test-restore                 # la más reciente
scripts/test-restore 2026-09-21_0330
```

Restaura la copia con `scripts/restore` en un proyecto de compose aparte
(`jarvis-restore-test`, con sus propios volúmenes y los puertos 15432 y 16333, y nunca en
`OPENCLAW_STATE_PATH`), compara con la instalación en marcha las filas de las tablas
principales de Jarvis y OpenProject, los puntos de cada colección de Qdrant, los ficheros
de OpenClaw y los secretos, y lo borra todo al terminar. Lo creado después de la copia
aparece como diferencia.

Resultado el 21-09-2026 en la VM (copia `2026-09-21_0845`): 14/14 comprobaciones iguales,
~30 s.
