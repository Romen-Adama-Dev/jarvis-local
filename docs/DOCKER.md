# Docker — imagen de la aplicación (perfil `app`)

Primera iteración del objetivo de portabilidad: la aplicación completa (API +
worker) empaquetada en una única imagen (`jarvis-local:latest`) que arranca
automáticamente, con migraciones incluidas. La infraestructura (Qdrant,
PostgreSQL, Redis) ya era Docker; con este perfil, todo el plano de datos y de
aplicación se levanta con Compose:

```bash
cp .env.example .env   # rellenar valores
docker compose --profile app up -d --build
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

## Diseño

* **Una imagen, dos servicios**: `api` y `worker` comparten la imagen; el
  entrypoint (`infra/docker/entrypoint.sh`) selecciona el modo. `api` ejecuta
  `alembic upgrade head` antes de arrancar, de modo que un despliegue desde
  cero queda migrado sin pasos manuales. `worker` arranca arq directamente y
  espera a que `api` esté healthy (las migraciones ya aplicadas).
* **Multi-stage con uv**: el builder resuelve `uv.lock` congelado
  (`uv sync --frozen --no-dev`); la imagen final es `python:3.12-slim` +
  `libmagic1`, sin toolchain. El código corre como usuario `jarvis` (uid
  1000), nunca root.
* **`network_mode: host`**, decisión deliberada y no un atajo: Ollama y
  AirLLM son servicios nativos ligados a `127.0.0.1` (requisito de seguridad:
  nada expuesto públicamente). Con red de host, los contenedores los alcanzan
  por loopback igual que el despliegue systemd, con el mismo `.env`, y la API
  del contenedor sigue ligada a `127.0.0.1`. La alternativa (bridge +
  `host.docker.internal`) exigiría re-exponer Ollama/AirLLM en la IP del
  puente, ampliando superficie.
* **Estado en volumen**: `/srv/jarvis` (documentos, caché de embeddings,
  logs) vive en el volumen `jarvis_srv`. Los healthchecks son los del resto
  del stack: HTTP `/health` para la API y `arq --check` (health key real de la
  cola) para el worker.
* El `.env` se inyecta en runtime (`env_file`); la imagen no contiene
  secretos (`.dockerignore` excluye `.env` y `.git`).

## Advertencia operativa

No ejecutes el perfil `app` en una máquina donde la API y el worker ya corren
por systemd: ambos workers consumirían la misma cola de Redis con sistemas de
archivos distintos (el volumen vs `/srv/jarvis` real) y las ingestas quedarían
repartidas de forma inconsistente. En este servidor el perfil `app` se validó
(build, arranque, `/health` y `/ready` con todas las dependencias en verde,
worker healthy conectado a la cola) y se detuvo; systemd sigue siendo el
despliegue de producción local.

## Puerto

`JARVIS_API_PORT` (por defecto 8000) controla el puerto de la API también en
el contenedor. Para la validación en este servidor se usó
`JARVIS_API_PORT=8010 docker compose --profile app up -d` por convivir con la
API de systemd en el 8000.

## Límites actuales y ampliaciones previstas

* **Ollama y AirLLM siguen siendo nativos** (systemd): contenedorizarlos exige
  el NVIDIA Container Toolkit y una imagen con torch/CUDA (~5 GiB); es la
  siguiente iteración natural del objetivo "clonar y levantar" en máquinas
  nuevas. En equipos sin GPU, la API funciona apuntando a cualquier endpoint
  Ollama accesible (`OLLAMA_HOST`).
* **OpenClaw** (Telegram) también queda fuera de la imagen por ahora.
* Publicar la imagen en un registry (GHCR) cuando el repositorio tenga remoto,
  para que "descargar y lanzar" no requiera build local.
