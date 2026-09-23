# OpenClaw — integración

OpenClaw es la capa de interacción de Jarvis: el agente que habla por Telegram y por el
panel web, y que llama a las capacidades de Jarvis a través de servidores MCP. Este
documento describe el **despliegue actual con Docker Compose**: servicio `openclaw`,
imagen construida desde `integrations/openclaw/Dockerfile`, y configuración generada en
cada arranque por `integrations/openclaw/docker-entrypoint.sh` a partir de
`integrations/openclaw/config/openclaw.template.json` (ver `docs/DOCKER.md`).

La instalación sin Docker (npm + systemd de usuario), con la que nació el proyecto, y
los incidentes de julio y septiembre de 2026 que explican muchas de estas decisiones
están en `docs/OPENCLAW-HISTORICO.md`.

## Configuración

Archivo: `~/.openclaw/openclaw.json` (JSON5/JSON, permisos `600`, fuera del repositorio — nunca se versiona porque contiene el token de Telegram y el token interno de Jarvis API).

Decisiones clave:

* **Modelo**: proveedor `custom` apuntando directamente al endpoint OpenAI-compatible de Ollama (`http://127.0.0.1:11434/v1`), con `OLLAMA_PRIMARY_MODEL`, que `scripts/select-models` elige según la VRAM (`docs/MODELS.md`; en la L4, `gemma4:26b-a4b-it-qat`; en la GTX 1070 original, `qwen2.5:7b-instruct-q4_K_M`). Ollama y Jarvis API ya cumplen "proveedor local" exigido por el prompt; no fue necesario levantar un endpoint OpenAI-compatible adicional en Jarvis API para esto.
* **`memory.search`**: activada con embeddings locales (`provider: ollama-embeddings`, modelo `embeddinggemma`; requiere `ollama` en `plugins.allow`). Por defecto OpenClaw usaría OpenAI, así que nunca se deja el proveedor sin fijar (principio "sin fallback a proveedores externos").
* **Sandbox**: `agents.defaults.sandbox.mode: "off"`. Se probó `"non-main"` (sandbox Docker para sesiones no principales) pero el host no soporta el aislamiento por namespaces que requiere (`bwrap: setting up uid map: Permission denied`, ver aviso de `openclaw doctor`), y con un único usuario autorizado no hay sesiones "no principales" reales que proteger. Si en el futuro se añaden más agentes/canales, revisar esta decisión.
* **`tools.deny`**: se deniegan `process`, `code_execution`, `browser`, `cron`, `nodes`, `gateway`, generación de imagen/música/vídeo, `tts`, las herramientas de sesiones y subagentes, entre otras (lista completa en la plantilla). `exec` **no** está denegado desde el 13-07: pasa por exec approvals (sección «Ejecución de comandos desde Telegram»).
* **`tools.sandbox.tools.alsoAllow`** (`jarvis-rag__*`, `jarvis-calendar__*`, `jarvis-email__*`, `jarvis-office__*` y las `wiki_*`): necesario para que las herramientas del servidor MCP sigan siendo visibles si en el futuro se reactiva el sandbox.
* **`gateway.auth`**: token generado automáticamente por `openclaw doctor --fix` (websocket del gateway protegido incluso en loopback).

## Workspace del agente (plantillas)

El repositorio es público, así que los archivos de `integrations/openclaw/workspace/` no
llevan datos personales: son **plantillas** con marcadores que el arranque sustituye.

| Marcador | De dónde sale | Si falta |
|---|---|---|
| `__OWNER__` | `JARVIS_OWNER_NAME` | `mi usuario` |
| `__OWNER_FULL__` | `JARVIS_OWNER_FULL_NAME` | `JARVIS_OWNER_NAME` |
| `__OWNER_TZ__` | `JARVIS_OWNER_TIMEZONE` | `TZ`, `CALENDAR_TIMEZONE`, `UTC` |
| `__SERVER_HW__` | CPU de `/proc/cpuinfo`, RAM de `/proc/meminfo` y GPU de `nvidia-smi`, detectados en el arranque | `servidor Linux` |

`integrations/openclaw/docker-entrypoint.sh` los renderiza en `~/.openclaw/workspace-jarvis`:
`AGENTS.md` (las reglas de trabajo) en **cada arranque**, de modo que editarlo a mano en el
volumen no sirve de nada —se edita la plantilla del repo—; y `SOUL.md`, `IDENTITY.md`,
`USER.md`, `TOOLS.md` y `HEARTBEAT.md` **solo la primera vez**, porque a partir de ahí son
del propietario y el propio agente los va completando (lo que aprende de ti no vuelve al
repo).

Al añadir texto a una plantilla, escribe `__OWNER__` en lugar de un nombre y no metas
correos, hostnames del tailnet ni rutas con el usuario real.

## Skill `jarvis-rag`

En vez de enseñar al agente a invocar `curl`/shell (lo cual violaría "no shell arbitrario"), `jarvis-rag` es un **servidor MCP** propio (`integrations/openclaw/skills/jarvis-rag/server.py`, con `mcp` como dependencia añadida al proyecto) que expone herramientas tipadas, cada una limitada a una llamada HTTP concreta contra Jarvis API:

| Herramienta MCP | Endpoint de Jarvis API | Uso |
|---|---|---|
| `jarvis_ask` | `POST /v1/rag/query` | Consulta normal (Ollama) |
| `jarvis_status` | `GET /health`, `GET /ready` | Salud del sistema |
| `jarvis_models` | `GET /v1/models` | Modelos disponibles |
| `jarvis_disk` | — (lee `shutil.disk_usage` sobre `/srv/jarvis` en el propio host) | Espacio de disco |
| `jarvis_jobs` | `GET /v1/jobs` | Trabajos activos |
| `jarvis_cancel_job` | `POST /v1/jobs/{id}/cancel` | Cancelar un trabajo |

La tabla recoge las herramientas originales; hoy hay más (subida y movimiento de documentos, documentos generados, actas, memoria, directorio de servicios). La lista vigente, con cuándo usar cada una, está en `integrations/openclaw/workspace/AGENTS.md` y en `integrations/openclaw/skills/jarvis-rag/SKILL.md`.

Registrado en `mcp.servers.jarvis-rag` de `openclaw.json`, lanzado con el Python del venv del repo (`<repo>/.venv/bin/python .../server.py`), con `JARVIS_API_URL`, `JARVIS_API_INTERNAL_TOKEN` y `JARVIS_DATA_ROOT` como variables de entorno del propio proceso MCP (nunca visibles para el modelo).

**Pendiente deliberadamente fuera de esta fase** (no se expone ninguna herramienta para esto todavía, para no saltarse la exigencia de confirmación explícita de acciones administrativas):

* Reinicio de servicios permitidos (`ollama`, `jarvis-api`, `jarvis-worker`) — requiere conectar `packages/security/confirmation.py` (`ConfirmationService`, ya implementado en la Fase 5) a un flujo de confirmación de dos pasos antes de exponerlo como herramienta.
* Reindexación desde el chat. (La subida de documentos ya está hecha: ver «Subida de documentos al RAG desde Telegram».)

## Skills de terceros (ClawHub)

Solo se cargan skills de terceros revisadas y copiadas en
`integrations/openclaw/skills-terceros/` (lista, versión, licencia, SHA-256 y descartes en
su `README.md`). OpenClaw las lee con `skills.load.extraDirs`, con la precedencia más
baja, así que no pueden tapar las propias ni las incluidas. No se instala nada desde
ClawHub al arrancar (`skills.entries.clawhub` sigue desactivada). Hoy: `agile-toolkit`
(retros, planificación de sprint, historias de usuario, métricas; solo conocimiento).
Comprobar: `docker compose exec openclaw openclaw skills info agile-toolkit`.

## Lecciones que siguen vigentes

Del despliegue original y del incidente de septiembre (detalle y mediciones en
`docs/OPENCLAW-HISTORICO.md`):

* **El prompt del sistema cuesta dinero en un modelo local.** Las skills propias de
  OpenClaw se dejan deshabilitadas (`skills.entries`) y el workspace se escribe corto y
  en español: las capacidades de Jarvis llegan por MCP, no por skills. Ante síntomas de
  "tool calls escritas como texto", idioma mezclado o `NO_REPLY` persistente, mide
  primero el tamaño del prompt compilado antes de culpar al modelo, y resetea la sesión
  con `/new` porque el historial contaminado perpetúa el fallo.
* **Las herramientas de orquestación multiagente se deniegan** (`sessions_*`,
  `subagents`, `agents_list`, `conversations_*`, `dashboard`, goals, `portal`…): además
  de engordar el prompt, inyectan en cada turno un bloque de sesiones activas que un
  modelo local toma por el tema de la conversación.
* **`heartbeat.target: "none"`**: si no, el heartbeat escribe avisos en el chat.
* **Adjuntos**: el plugin `document-extract` va activado; sin él el modelo solo ve
  `[Attachment could not be read]`. Nunca ve la ruta en disco, así que `jarvis_upload`
  acepta el nombre del adjunto y lo localiza en `media/inbound/`.
* **Ventana de contexto de Ollama**: el prompt de OpenClaw ronda los 25k tokens; con el
  `num_ctx` por defecto (4096) se truncaba en silencio y los fallos parecían del modelo.
  `OLLAMA_CONTEXT_LENGTH` se fija en el `.env` y `quickstart` avisa si falta.
* **Diagnóstico**: la transcripción real está en
  `~/.openclaw/agents/main/agent/openclaw-agent.sqlite` (tabla `transcript_events`);
  `openclaw agent --session-key agent:main:<x>` prueba en una sesión aislada sin
  contaminar la de Telegram.

## Ejecución de comandos desde Telegram (exec approvals)

Decisión (2026-07-13, a petición del propietario): se habilita `exec` en el gateway, sustituyendo la prohibición total de shell por un **modelo de aprobación explícita**. Esto revisa el principio original "no shell arbitrario desde Telegram" de forma defendible:

* Política: `openclaw exec-policy set --host gateway --security allowlist --ask on-miss --ask-fallback deny`.
* Lista blanca (en `~/.openclaw/exec-approvals.json`, agente `main`): solo lectura — `uptime`, `uname`, `df`, `free`, `date`, `whoami`, `ls`, `du`, `ps` (en Docker la aplica `docker-entrypoint.sh`; la instalación sin Docker añade `nvidia-smi` y `ollama`). Corren sin preguntar.
* **Cualquier otro comando** queda retenido y Telegram muestra botones de aprobación nativos (`/approve`); sin interfaz disponible, se deniega (`askFallback: deny`). Verificado: un `touch` no listado no se ejecutó sin aprobación.
* Los comandos corren dentro del contenedor, con el usuario sin privilegios del despliegue (`JARVIS_UID`), nunca root; el contenedor no tiene `sudo`.
* Sigue habiendo un único usuario de Telegram autorizado (allowlist por ID) y auditoría de sesión.
* `write`/`edit` permiten crear y modificar documentos directamente (verificado con `ideas-tfm.md`).

Riesgo aceptado y mitigación: un documento malicioso del RAG podría intentar inyectar comandos; la allowlist solo contiene lecturas inofensivas y todo lo demás pasa por confirmación humana del propietario.

## Búsqueda web local (SearXNG)

La búsqueda usa **SearXNG autohosteado** (servicio por defecto de `compose.yml`, sin perfil; imagen fijada por digest, solo `127.0.0.1:8888`, formato JSON habilitado en `infra/compose/searxng/settings.yml`). OpenClaw lo usa mediante el plugin oficial `@openclaw/searxng-plugin` (`tools.web.search.provider: "searxng"`, `plugins.allow: ["searxng"]`). Las consultas de búsqueda salen a los buscadores agregados desde el servidor propio, sin API keys ni proveedores comerciales; la inferencia sigue siendo 100% local.

El agente **no** tiene `web_search` libre (está en `tools.deny`): internet va después de lo interno y con dos permisos del usuario. `jarvis_web_sources` (jarvis-rag) consulta SearXNG y devuelve solo la lista de fuentes, sin contenido; `jarvis_web_read` entrega el extracto de las que el usuario apruebe. El flujo completo está en `AGENTS.md` ("Primero lo interno; internet solo con permiso").

```bash
docker compose up -d searxng
```

## Voz (STT y TTS locales)

* **Notas de voz entrantes**: `tools.media.audio` ejecuta `whisper-cli` (whisper.cpp compilado en la propia imagen, solo CPU: la GPU la ocupa Ollama) con `ggml-small-q5_1` (~5 s por nota en CPU, detección automática de idioma). `echoTranscript` devuelve la transcripción al chat antes de procesarla; los comandos `/ask` etc. funcionan también dictados.
* **Respuestas con voz**: `messages.tts` con proveedor CLI local — wrapper `jarvis-tts` que invoca Piper (voz `es_ES-davefx-medium`). Los modelos de whisper y Piper se descargan al construir la imagen. Modo `inbound`: Jarvis responde con audio solo cuando el mensaje llegó como nota de voz; `/tts on|off` lo cambia por chat.
* Validado con round-trip local: audio generado por Piper transcrito correctamente por whisper.cpp.
* **ffmpeg es imprescindible**: las notas de voz de Telegram llegan en ogg/opus, que whisper.cpp no decodifica; OpenClaw las convierte con ffmpeg antes de invocar el CLI. Sin ffmpeg, el log muestra `media-understanding audio: failed reason=ffmpeg not found` y la voz "no funciona" (incidente 2026-07-13, resuelto con `apt install ffmpeg`).

## Correo y calendario

El correo va por IMAP/SMTP y el calendario por OpenProject o CalDAV, con las skills MCP
`jarvis-email` y `jarvis-calendar`: ver `docs/EMAIL.md` y `docs/CALENDAR.md`. Los
borradores se enseñan al propietario y se envían solo tras un "sí" explícito, con un
token de confirmación que caduca.

La integración anterior con `gog` (CLI de Google Workspace con OAuth), que se usó hasta
septiembre de 2026, está descrita en `docs/OPENCLAW-HISTORICO.md`.

## Subida de documentos al RAG desde Telegram

La herramienta MCP `jarvis_upload` (en `integrations/openclaw/skills/jarvis-rag/server.py`) sube un archivo a `POST /v1/documents`. OpenClaw deja los adjuntos de Telegram en `media/inbound/` del workspace y el agente pasa esa ruta a la herramienta. Protecciones: allowlist de directorios de origen (media del workspace, `~/jarvis-inbox`, `/srv/jarvis/documents`), extensiones soportadas por el RAG, y límite de 50 MiB; la API además valida MIME real, tamaño y duplicados por SHA-256. Verificado end-to-end (criterios 11-14 de aceptación): subida → indexación (5 chunks) → respuesta citando documento y sección → rechazo sin evidencia.

## Guía de bienvenida en /new y /reset

Hook interno gestionado `nueva-sesion-ayuda` (`~/.openclaw/hooks/`, fuente en `integrations/openclaw/hooks/`): al ejecutar `/new` o `/reset`, empuja un mensaje largo con todas las herramientas, usos y comandos disponibles (`event.messages.push`), que Telegram entrega junto al aviso de sesión nueva. El handler debe ser `.js` (el loader de hooks gestionados no acepta `.ts`). Lo copia y lo habilita `docker-entrypoint.sh` en cada arranque; nota: al activar hooks internos, el gateway también carga los hooks bundled (p. ej. `session-memory`, que guarda contexto de sesión en `memory/` al hacer `/new`).
