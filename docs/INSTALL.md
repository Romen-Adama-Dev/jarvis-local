# Instalación reproducible

Dos caminos, según lo que quieras probar. Ambos parten de `cp .env.example .env`.

## Camino rápido: solo la aplicación, con Docker

Para evaluar la API/RAG sin montar el despliegue completo de producción:

```bash
scripts/quickstart
```

Prepara `.env` (genera los secretos locales que faltan, detecta la GPU y
elige el par de modelos Ollama según `docs/BENCHMARKS.md`) y levanta el
perfil `app` de Docker Compose (API + worker + Qdrant + PostgreSQL + Redis).
Ver `docs/DOCKER.md` para el diseño de ese perfil y sus límites actuales
(Ollama sigue siendo un servicio nativo, no contenerizado).

Si prefieres los pasos a mano: `docs/DOCKER.md` los detalla.

## Camino completo: servidor bare-metal reproducible (producción local)

El despliegue real de este proyecto (ver `docs/ARCHITECTURE.md` y
`docs/SECURITY.md`) corre Ollama y AirLLM nativos por GPU y la API/worker
como servicios systemd, no en Docker. Orden de instalación en un Ubuntu
Server limpio:

```bash
# 1. Usuario de servicio, /srv/jarvis, UFW (deniega todo salvo SSH)
scripts/bootstrap-server

# 2. Docker Engine (para Qdrant, PostgreSQL, Redis; ver infra/systemd)
scripts/install-docker

# 3. Ollama nativo con soporte GPU (requiere driver NVIDIA ya cargado)
scripts/install-ollama

# 4. Elegir/confirmar los modelos Ollama para esta GPU
scripts/select-models --dry-run
#   sin --dry-run escribe .env; scripts/quickstart también lo invoca

# 5. AirLLM (opcional, modo /deep; ver docs/AIRLLM.md)
scripts/install-airllm

# 6. Telegram + OpenClaw (opcional, capa de interacción; ver docs/TELEGRAM.md
#    y docs/OPENCLAW.md)
scripts/configure-telegram
scripts/install-openclaw

# 6.1 Microsoft Teams (opcional, segundo canal; requiere Azure Bot ya
#     registrado y túnel hacia el messaging endpoint; ver docs/TEAMS.md)
scripts/configure-teams

# 7. Generación de documentos en PDF (opcional; ver docs/DOCGEN.md). Sin este
#    paso, la generación de documentos sigue funcionando en md/docx/pptx.
scripts/install-docgen

# 8. Sincroniza el código a /srv/jarvis/app, aplica migraciones y arranca
#    jarvis-api.service / jarvis-worker.service (y airllm.service si aplica)
scripts/deploy
```

Cada script es idempotente: puedes repetir la secuencia completa tras un
`git pull` para desplegar cambios (`scripts/deploy` es el paso que se repite
normalmente; los demás solo la primera vez o al cambiar de hardware).

## Verificación

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

`/ready` reporta el estado de PostgreSQL, Redis y Qdrant. Ver
`docs/ACCEPTANCE.md` para la lista completa de criterios verificados.

## Requisitos

* Ubuntu 26.04 LTS
* Python 3.12 (gestionado por `uv`)
* Docker Engine + Docker Compose
* GPU NVIDIA con driver instalado (opcional pero recomendado; ver
  `docs/BENCHMARKS.md` para el hardware sobre el que está medido el
  rendimiento)
