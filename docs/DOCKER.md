# Docker compose: despliegue completo

Todo Jarvis (modelo local, RAG, agente con Telegram y voz, búsqueda web, memoria) se
levanta con Docker Compose, sin instalar nada más en el host:

```bash
git clone https://github.com/Romen-Adama-Dev/jarvis-local.git
cd jarvis-local
cp .env.example .env   # rellena TELEGRAM_BOT_TOKEN y TELEGRAM_AUTHORIZED_USER_IDS
docker compose up -d
```

El primer arranque construye las imágenes (unos 10-15 minutos) y descarga el modelo
elegido para tu GPU (15 GB en una GPU de 24 GB). Para seguirlo:
`docker compose logs -f ollama-pull openclaw`. Después, háblale al bot por Telegram o
abre la interfaz web (ver más abajo).

Sin `.env` también arranca: Telegram queda desactivado y la interfaz web funciona.

## Requisitos

* Linux x86-64 con Docker Engine y Compose v2.30 o superior.
* GPU NVIDIA con driver y [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`).
  Sin GPU: `docker compose -f compose.yml -f compose.cpu.yml up -d` (modelo pequeño,
  mucho más lento).
* ~40 GB de disco libres.
* Un bot de Telegram (BotFather) y tu ID numérico de Telegram.

## Servicios

| Servicio | Qué hace |
|---|---|
| `init` | Primer paso de cada arranque: genera los secretos que falten y elige los modelos según la VRAM (`scripts/select-models`). Termina y sale |
| `ollama` | Modelos locales en GPU (`ollama/ollama`, versión fijada) |
| `ollama-pull` | Descarga los modelos si faltan (el elegido y `embeddinggemma` para la memoria). Termina y sale |
| `api` / `worker` | API de Jarvis (RAG, documentos, correo, calendario) y cola de trabajos; `api` aplica las migraciones al arrancar |
| `openclaw` | Agente y canales (Telegram, interfaz web), skills MCP, voz (whisper.cpp + Piper) y memoria/Obsidian. Imagen `integrations/openclaw/Dockerfile` |
| `postgres`, `redis`, `qdrant` | Datos |
| `searxng` | Búsqueda web del agente |

Perfiles opcionales (`COMPOSE_PROFILES` en `.env`, separados por comas):

| Perfil | Servicios |
|---|---|
| `tailscale` | Interfaz web de OpenClaw por HTTPS desde tu tailnet (`TS_AUTHKEY`; ver abajo) |
| `vault` | `vault-sync`: vault de Obsidian en un repo git privado (`VAULT_GIT_URL`, `VAULT_SSH_KEY_PATH`; ver `docs/MEMORY.md`) |
| `livesync` | `couchdb`, `livesync-init` y `livesync-bridge`: Obsidian en el móvil y el portátil en tiempo real, por Tailscale (`docs/OBSIDIAN.md`) |
| `pm` | OpenProject (`openproject`, `openproject-worker`, `openproject-setup`, `openproject-db-init`, `openproject-cache`): tableros, tickets, Gantt, hitos y riesgos manejados desde Telegram con la skill `jarvis-pm`; con `tailscale`, en `https://<nombre>.ts.net:8445` (`docs/OPENPROJECT.md`) |
| `monitoring` | Prometheus + Grafana |
| `assistant` | changedetection |
| `automation` | n8n |
| `webui` | Open WebUI (habla con Ollama directamente, sin RAG ni herramientas de Jarvis) |

Orden de arranque: `init` → `postgres`/`searxng`/`ollama` → `ollama-pull` y `api` →
`worker` y `openclaw`.

## Configuración y secretos

* **Secretos**: `init` genera la contraseña de PostgreSQL, el token interno de la API,
  el secreto de SearXNG y el token del gateway en el volumen `jarvis_runtime`
  (`/run/jarvis`), que el resto de servicios lee al arrancar. Si un valor está en `.env`,
  tiene prioridad y se copia al volumen: así una instalación existente conserva los
  suyos. No cambies `POSTGRES_PASSWORD` después del primer arranque (la base de datos ya
  se inicializó con la anterior).
* **Modelos**: con `OLLAMA_PRIMARY_MODEL` vacío, `init` detecta la VRAM y elige nivel
  (`docs/MODELS.md`); `JARVIS_MODEL_TIER` fuerza un nivel concreto. Con
  `OLLAMA_PRUNE_UNUSED=true`, `ollama-pull` borra los modelos que no estén en uso.
* **OpenClaw**: `openclaw.json` se genera en cada arranque desde
  `integrations/openclaw/config/openclaw.template.json` y `.env`, y `AGENTS.md` se copia
  desde `integrations/openclaw/workspace/`. La configuración vive en el repo: los cambios
  hechos a mano en el volumen se pierden al reiniciar.
* **Correo y calendario**: variables `MAIL_*`, `IMAP_*`, `SMTP_*` y `CALDAV_*` de `.env`
  (`docs/EMAIL.md`, `docs/CALENDAR.md`) y `docker compose up -d api worker`.
  `scripts/configure-mail` las rellena y prueba la conexión, pero necesita `uv` en el
  host.

## Interfaz web de OpenClaw

El gateway escucha solo en `127.0.0.1:18789` del servidor. Token para entrar:

```bash
docker compose exec openclaw cat /run/jarvis/openclaw_gateway_token
```

### Desde tu tailnet (recomendado)

Con el perfil `tailscale`, el panel queda en `https://jarvis.<tu-tailnet>.ts.net` desde el
móvil o el portátil, sin abrir puertos. Configuración paso a paso, funcionamiento y
problemas frecuentes en `docs/ACCESO-REMOTO.md`.

### Por túnel SSH

```bash
ssh -L 18789:127.0.0.1:18789 usuario@servidor
# abre http://localhost:18789 y pega el token
```

## Obsidian

Con los perfiles `tailscale` y `livesync`, el vault de memoria se abre y edita desde
Obsidian en el móvil o el portátil con sincronización en tiempo real: `docs/OBSIDIAN.md`.

## Gestión de proyectos

Con el perfil `pm`, OpenProject lleva tareas, hitos, riesgos y el seguimiento de cada
proyecto, organizado por empresas; Jarvis lo maneja desde Telegram y tú lo ves en el
navegador por Tailscale: `docs/OPENPROJECT.md`.

## Actualizar

```bash
git pull
docker compose up -d --build
```

## Reutilizar una instalación previa en el host

Para pasar a compose un servidor que ya ejecutaba Ollama y OpenClaw con systemd, sin
volver a descargar modelos ni perder sesiones, memoria o el vault:

```bash
# .env
OLLAMA_MODELS_PATH=/usr/share/ollama/.ollama/models
OPENCLAW_STATE_PATH=/home/<usuario>/.openclaw
JARVIS_UID=<id -u>
JARVIS_GID=<id -g>
TELEGRAM_BOT_TOKEN=...            # el de ~/.openclaw/secrets/telegram_bot_token
TELEGRAM_AUTHORIZED_USER_IDS=...
OPENCLAW_GATEWAY_TOKEN=...        # el de ~/.openclaw/openclaw.json, para no cambiarlo

# parar los servicios del host (liberan los puertos 11434 y 18789)
systemctl --user disable --now openclaw-gateway.service jarvis-vault-sync.timer
sudo systemctl disable --now ollama
docker compose up -d
```

## Diseño

* **`network_mode: host`** en `ollama`, `openclaw`, `api` y `worker`: se hablan por
  `127.0.0.1` igual que en el despliegue en host, con la misma plantilla de OpenClaw, y
  nada queda expuesto fuera del loopback. PostgreSQL, Redis, Qdrant y SearXNG van en una
  red bridge y publican sus puertos solo en `127.0.0.1`. Por eso el despliegue es solo
  Linux.
* **Imágenes**: `jarvis-local` (API, worker e init; `python:3.12-slim` + pandoc/XeLaTeX)
  y `jarvis-openclaw` (Node 24 + OpenClaw fijado, el venv de las skills MCP, whisper.cpp
  compilado para CPU con AVX2 y Piper con la voz `es_ES-davefx-medium`). Ninguna
  contiene secretos (`.dockerignore` excluye `.env`).
* **Usuarios**: `api`/`worker` corren como `jarvis` (uid 1000); `openclaw` y
  `vault-sync` con `JARVIS_UID`/`JARVIS_GID`, para poder reutilizar un `~/.openclaw` del
  host; `init` corre como root para escribir el volumen de secretos.
* **Rendimiento**: `OLLAMA_NUM_PARALLEL` (4) permite atender a la vez al agente, al RAG y
  a las secciones de un documento (`DOCGEN_CONCURRENCY`, también 4); flash attention y
  caché KV en `q8_0`.

## Límites

* AirLLM (`/deep`) no está contenerizado (`docs/AIRLLM.md`).
* whisper.cpp se compila con AVX2; en CPUs anteriores a ~2013 construye la imagen con
  `--build-arg WHISPER_AVX2=OFF`.
* Las imágenes se construyen en local; publicarlas en GHCR evitaría el build del primer
  arranque.
