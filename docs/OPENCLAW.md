# OpenClaw — integración

## Instalación

OpenClaw (`openclaw/openclaw`, licencia MIT) se instala solo para el usuario humano de desarrollo (`jarvis`, uid 1000), nunca para `jarvis-svc`: es el plano de control personal desde el móvil, no un servicio de la plataforma.

```bash
npm config set prefix ~/.npm-global
npm install -g openclaw@latest
export PATH=~/.npm-global/bin:$PATH   # añadido a ~/.bashrc
```

Requiere Node.js ≥24.16 (mínimo de `openclaw@latest`, sube de vez en cuando —
comprueba `engines.node` si `scripts/install-openclaw` falla con `EBADENGINE`).
Ubuntu 22.04/24.04 no lo traen en sus repos oficiales: `scripts/install-openclaw`
lo instala vía NodeSource automáticamente.

## Configuración

Archivo: `~/.openclaw/openclaw.json` (JSON5/JSON, permisos `600`, fuera del repositorio — nunca se versiona porque contiene el token de Telegram y el token interno de Jarvis API).

Decisiones clave:

* **Modelo**: proveedor `custom` apuntando directamente al endpoint OpenAI-compatible de Ollama (`http://127.0.0.1:11434/v1`), con los dos modelos seleccionados en `docs/BENCHMARKS.md` (`qwen2.5:7b-instruct-q4_K_M` rápido por defecto, `llama3.1:8b-instruct-q4_K_M` potente disponible). Ollama y Jarvis API ya cumplen "proveedor local" exigido por el prompt; no fue necesario levantar un endpoint OpenAI-compatible adicional en Jarvis API para esto.
* **`agents.defaults.memorySearch.enabled: false`**: por defecto OpenClaw usa OpenAI para búsqueda semántica de memoria. Se desactiva explícitamente para no violar el principio "sin fallback a proveedores externos".
* **Sandbox**: `agents.defaults.sandbox.mode: "off"`. Se probó `"non-main"` (sandbox Docker para sesiones no principales) pero el host no soporta el aislamiento por namespaces que requiere (`bwrap: setting up uid map: Permission denied`, ver aviso de `openclaw doctor`), y con un único usuario autorizado no hay sesiones "no principales" reales que proteger. Si en el futuro se añaden más agentes/canales, revisar esta decisión.
* **`tools.deny`**: se deniega explícitamente `exec, process, code_execution, browser, cron, nodes, gateway, image_generate, music_generate, video_generate, tts`. Esto es lo que garantiza "no ejecución de shell arbitraria desde Telegram": el agente no tiene ninguna vía de shell, solo las herramientas MCP explícitas de `jarvis-rag`.
* **`tools.sandbox.tools.alsoAllow: ["jarvis-rag__*"]`**: necesario para que las herramientas del servidor MCP sigan siendo visibles si en el futuro se reactiva el sandbox.
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
| `jarvis_deep` | `POST /v1/rag/deep-query` | Consulta profunda (AirLLM, Fase 8) |
| `jarvis_status` | `GET /health`, `GET /ready` | Salud del sistema |
| `jarvis_models` | `GET /v1/models` | Modelos disponibles |
| `jarvis_disk` | — (lee `shutil.disk_usage` sobre `/srv/jarvis` en el propio host) | Espacio de disco |
| `jarvis_jobs` | `GET /v1/jobs` | Trabajos activos |
| `jarvis_cancel_job` | `POST /v1/jobs/{id}/cancel` | Cancelar un trabajo |

Registrado en `mcp.servers.jarvis-rag` de `openclaw.json`, lanzado vía `uv run --frozen --project /home/jarvis/jarvis-local python .../server.py`, con `JARVIS_API_URL`, `JARVIS_API_INTERNAL_TOKEN` y `JARVIS_DATA_ROOT` como variables de entorno del propio proceso MCP (nunca visibles para el modelo).

**Pendiente deliberadamente fuera de esta fase** (no se expone ninguna herramienta para esto todavía, para no saltarse la exigencia de confirmación explícita de acciones administrativas):

* Reinicio de servicios permitidos (`ollama`, `jarvis-api`, `jarvis-worker`) — requiere conectar `packages/security/confirmation.py` (`ConfirmationService`, ya implementado en la Fase 5) a un flujo de confirmación de dos pasos antes de exponerlo como herramienta.
* Subida de documentos (`/v1/documents`) y reindexación — Telegram permite adjuntar archivos; falta implementar la recepción del adjunto en la skill.

## Skills de terceros (ClawHub)

Solo se cargan skills de terceros revisadas y copiadas en
`integrations/openclaw/skills-terceros/` (lista, versión, licencia, SHA-256 y descartes en
su `README.md`). OpenClaw las lee con `skills.load.extraDirs`, con la precedencia más
baja, así que no pueden tapar las propias ni las incluidas. No se instala nada desde
ClawHub al arrancar (`skills.entries.clawhub` sigue desactivada). Hoy: `agile-toolkit`
(retros, planificación de sprint, historias de usuario, métricas; solo conocimiento).
Comprobar: `docker compose exec openclaw openclaw skills info agile-toolkit`.

## OpenClaw 2026.9 (despliegue 2026-09-15, VM `jarvis-gpu-us`, Ubuntu 22.04)

Lo aprendido al desplegar desde cero sobre una versión de OpenClaw mucho más
nueva que la del despliegue original, en el orden en que fue apareciendo:

* **Node ≥ 24.16** (`engines.node` del paquete; el `nodejs` de apt en 22.04 es
  v12). `scripts/install-openclaw` lo resuelve; en esta VM se usó `nvm`
  (`~/.nvm`, alias `default` 24) y el `openclaw gateway install` generó el
  unit apuntando al binario de nvm.
* **`whisper.cpp` no está en los repos apt de 22.04**: `scripts/install-openclaw`
  lo compila desde fuente (tag fijado `v1.8.3`, solo CPU porque la GPU la
  ocupa Ollama) e instala `whisper-cli` en `/usr/local/bin` con sus `.so` en
  `/usr/local/lib/whisper.cpp` (ld.so.conf). La plantilla usa el placeholder
  `__WHISPER_CLI__` (resuelto por `configure-telegram` con `command -v`).
  Validado: wav de Piper (`es_ES-davefx-medium`) → ogg/opus → ffmpeg →
  whisper `small-q5_1` transcribe exacto; ~20 s la primera nota (carga del
  modelo + CPU compartida con el 10 % de Ollama), después menos.
* **Esquema de config nuevo**: `openclaw doctor --fix` migra
  `agents.defaults.memorySearch` → `memory.search`, `tools.exec.security/ask`
  → `tools.exec.mode`, `tools.media.audio.models` → `tools.media.models` con
  `capabilities`, y retira `compaction.reserveTokens*`. La plantilla ya está
  en el esquema nuevo. `configure-telegram` sustituye además `__HOME__`,
  `__REPO_DIR__` y el modelo/contexto de `.env` (la plantilla antigua tenía
  `/home/jarvis` y `qwen3:4b` fijos, que no existían en esta VM).
* **Herramientas de orquestación multiagente** (`sessions_*`, `subagents`,
  `agents_list`, `conversations_*`, `dashboard`, goals, `portal`…): vienen
  activas por defecto y, además de engordar el prompt, inyectan en cada turno
  un bloque `Active exec sessions / Active Subagents` que un modelo local
  toma como el tema de la conversación. Se deniegan todas en `tools.deny`.
  Pendiente decidir si denegar también `openclaw` (permite al propio bot
  reiniciar el gateway: ocurrió en producción).
* **`heartbeat.target: "none"`**: sin esto el heartbeat escribe avisos en el
  chat de Telegram.
* **Adjuntos**: el plugin bundled `document-extract` viene desactivado; sin él
  el modelo solo ve `[Attachment could not be read]`. Activado, el modelo
  recibe `<file name="NOMBRE">` con un extracto (`pdfMaxPages: 3`, suficiente
  para identificar el documento sin llenar el contexto). Nunca ve la ruta en
  disco, así que `jarvis_upload` acepta el nombre del adjunto y lo localiza en
  `media/inbound/` (OpenClaw guarda `[input-]<nombre saneado>---<uuid>.ext`,
  recortando nombres largos).
* **Contexto de Ollama (la causa de fondo de todo lo anterior "sin explicación")**:
  `scripts/quickstart` no instala el override de systemd de
  `scripts/install-ollama`, así que el Ollama del host servía con
  `num_ctx=4096`; el prompt de OpenClaw ronda 25k tokens y se truncaba en
  silencio (incidente nº 2 de `docs/TELEGRAM.md`). `quickstart` ahora avisa
  si falta `OLLAMA_CONTEXT_LENGTH` en el servicio. Con 32k, `qwen2.5:32b` no
  cabe entero en una L4 (24 GB frente a 23): ~10 % en CPU, primer turno ~60 s.
* **Diagnóstico**: la transcripción real está en
  `~/.openclaw/agents/main/agent/openclaw-agent.sqlite` (tabla
  `transcript_events`); `openclaw agent --session-key agent:main:<x>` prueba en
  una sesión aislada sin contaminar la de Telegram; `/new` tras cualquier
  cambio de prompt, porque el historial contaminado perpetúa el fallo.

## Tamaño del prompt y modelos pequeños

Incidente real (2026-07-13): con la configuración por defecto, el system prompt compilado por OpenClaw medía ~34.500 caracteres (~9-10k tokens): ~6.800 de la lista `<available_skills>` (18 skills irrelevantes: notion, weather, meme-maker, tmux…) y ~14.600 de las plantillas por defecto del workspace (`AGENTS.md`/`SOUL.md`/`TOOLS.md` con secciones de heartbeat, group chats, ejemplos de cámaras/TTS…). Con ese volumen de instrucciones en inglés, `qwen2.5:7b-instruct-q4_K_M` colapsaba: escribía las llamadas a herramientas como texto plano en Telegram (`{name: web_search, arguments: …}`), mezclaba chino y se quedaba atascado respondiendo `NO_REPLY` (se auto-envenenaba: una alucinación con "responde solo NO_REPLY" entraba en su propio historial).

Mitigación aplicada y verificada:

* Todas las skills de OpenClaw deshabilitadas en `skills.entries` (47 entradas `enabled: false`) — las capacidades de Jarvis llegan por MCP, no por skills.
* `AGENTS.md`, `SOUL.md` y `TOOLS.md` del workspace reescritos: solo reglas específicas de Jarvis, en español, sin plantilla.
* Resultado: prompt de ~17.200 caracteres, tool calling nativo funcionando (verificado en trayectoria: `toolCall` reales a `jarvis_status`/`jarvis_models`) y respuestas en español sin fugas de formato.

Regla general: cada sección añadida al prompt tiene coste real en un 7B cuantizado; ante síntomas de "tool calls como texto", idioma mezclado o `NO_REPLY` persistente, medir primero el tamaño del prompt en la trayectoria (`context.compiled`) antes de culpar al modelo. Tras un episodio así, resetear la sesión (`/new`), porque el historial contaminado perpetúa el fallo.

## Latencia (2026-07-13)

Medición inicial: un turno trivial de Telegram tardaba ~34 s. Desglose real (trayectoria + journal de Ollama):

* Cada turno envía ~11-13k tokens (prompt de sistema + esquemas de herramientas + historial) y Ollama los reprocesaba **enteros** (~28 s a ~400-500 tok/s de prefill en la GTX 1070).
* OpenClaw compactaba la sesión **después de casi cada turno**: el umbral es `contextTokens > contextWindow − reserveTokens` y el *floor* por defecto de `reserveTokens` es 20.000 → con ventana de 32.768 compactaba a partir de ~12.7k tokens, es decir, siempre. Cada compactación es otra llamada al LLM con todo el transcript (15-16k tokens).
* `OLLAMA_KEEP_ALIVE=5m` descargaba el modelo tras 5 min → arranque frío en la primera consulta.

Cambios aplicados y medidos:

| Cambio | Efecto medido |
|---|---|
| `agents.defaults.compaction: {reserveTokens: 6144, reserveTokensFloor: 0, keepRecentTokens: 8192}` | Compactación pasa de "cada turno" a rara (umbral ~26.6k tokens); desaparece el error `compaction failed: Already compacted` |
| Modelo principal → `qwen3:4b-instruct-2507-q4_K_M` | Prefill 692 tok/s (vs 515), generación 41.7 tok/s (vs 28.7 con 17k de prompt); 5.2 GB VRAM (vs 6.2); la arquitectura qwen3 sí soporta flash attention en Ollama, qwen2.5 no |
| `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` | KV cache a mitad de memoria; requisito para lo anterior |
| `OLLAMA_KEEP_ALIVE=-1` | Sin descargas del modelo (servidor dedicado, un solo modelo cargado) |

Con la compactación arreglada, la caché de prefijo de Ollama por fin actúa: en turnos consecutivos reutiliza ~12.9k tokens cacheados y solo procesa el delta (~40 tokens). Turno completo por CLI: 11-15 s, de los que ~6 s son el arranque del propio CLI de node — desde Telegram (gateway residente) quedan ~5-9 s por turno. `qwen2.5:7b` y `llama3.1:8b` siguen disponibles como modelos alternativos.

## Ejecución de comandos desde Telegram (exec approvals)

Decisión (2026-07-13, a petición del propietario): se habilita `exec` en el gateway, sustituyendo la prohibición total de shell por un **modelo de aprobación explícita**. Esto revisa el principio original "no shell arbitrario desde Telegram" de forma defendible:

* Política: `openclaw exec-policy set --host gateway --security allowlist --ask on-miss --ask-fallback deny`.
* Lista blanca (en `~/.openclaw/exec-approvals.json`, agente `main`): solo lectura — `uptime`, `uname`, `df`, `free`, `date`, `whoami`, `ls`, `du`, `ps`, `nvidia-smi`, `ollama`. Corren sin preguntar.
* **Cualquier otro comando** queda retenido y Telegram muestra botones de aprobación nativos (`/approve`); sin interfaz disponible, se deniega (`askFallback: deny`). Verificado: un `touch` no listado no se ejecutó sin aprobación.
* Los comandos corren como usuario `jarvis`, nunca root; una escalada `sudo` requeriría aprobación explícita del propietario en cada ocasión.
* Sigue habiendo un único usuario de Telegram autorizado (allowlist por ID) y auditoría de sesión.
* `write`/`edit` permiten crear y modificar documentos directamente (verificado con `ideas-tfm.md`).

Riesgo aceptado y mitigación: un documento malicioso del RAG podría intentar inyectar comandos; la allowlist solo contiene lecturas inofensivas y todo lo demás pasa por confirmación humana del propietario.

## Búsqueda web local (SearXNG)

`web_search` está habilitado usando **SearXNG autohosteado** (perfil `assistant` de `compose.yml`, imagen fijada por digest, solo `127.0.0.1:8888`, formato JSON habilitado en `infra/compose/searxng/settings.yml`). OpenClaw lo usa mediante el plugin oficial `@openclaw/searxng-plugin` (`tools.web.search.provider: "searxng"`, `plugins.allow: ["searxng"]`). Las consultas de búsqueda salen a los buscadores agregados desde el servidor propio, sin API keys ni proveedores comerciales; la inferencia sigue siendo 100% local.

```bash
docker compose --profile assistant up -d searxng
```

## Voz (STT y TTS locales)

* **Notas de voz entrantes**: `tools.media.audio` ejecuta `whisper-cli` (whisper.cpp, paquete de Ubuntu) con `ggml-small-q5_1` desde `/srv/jarvis/models/whisper` (~5 s por nota en CPU, detección automática de idioma). `echoTranscript` devuelve la transcripción al chat antes de procesarla; los comandos `/ask` etc. funcionan también dictados.
* **Respuestas con voz**: `messages.tts` con proveedor CLI local — wrapper `jarvis-tts` que invoca Piper (voz `es_ES-davefx-medium`, en `/srv/jarvis/models/piper`). Modo `inbound`: Jarvis responde con audio solo cuando el mensaje llegó como nota de voz; `/tts on|off` lo cambia por chat.
* Validado con round-trip local: audio generado por Piper transcrito correctamente por whisper.cpp.
* **ffmpeg es imprescindible**: las notas de voz de Telegram llegan en ogg/opus, que whisper.cpp no decodifica; OpenClaw las convierte con ffmpeg antes de invocar el CLI. Sin ffmpeg, el log muestra `media-understanding audio: failed reason=ffmpeg not found` y la voz "no funciona" (incidente 2026-07-13, resuelto con `apt install ffmpeg`).

## Correo y calendario (gog)

`gog` v0.34.0 (CLI MIT de Google Workspace del propio proyecto OpenClaw: Gmail, Calendar, Drive, Contactos) está instalado en `~/.local/bin/gog`. Integración en dos niveles:

* **Lecturas sin fricción**: wrapper `~/.local/bin/gog-read` (fuente en `integrations/openclaw/config/gog-read`, instalado y allowlistado por `scripts/configure-telegram`). Fuerza `--readonly` (bloquea mutaciones a nivel de API de Google, no solo de prompt) y `--wrap-untrusted` (marca el contenido de correos como dato no confiable en la salida, mitigando prompt injection por email). El agente lo usa para buscar/leer correo y listar eventos sin pedir aprobación.
* **Escrituras siempre confirmadas**: el binario `gog` completo **no** está en la allowlist — enviar correos, etiquetar, crear/mover/borrar eventos dispara los botones de aprobación de OpenClaw en Telegram, y las reglas del workspace (`AGENTS.md`) exigen además resumen previo (destinatario/asunto/cuerpo o título/fecha del evento) y "sí" explícito en el chat. Doble puerta: regla de prompt + aprobación de exec fuera del LLM.

La skill `gog` de OpenClaw sigue deshabilitada a propósito: añadiría un bloque grande al prompt del sistema (ver incidente de prompt gigante con modelos 7B) y las reglas de `AGENTS.md` bastan.

### Autorización OAuth (paso único del propietario)

`gog auth list` debe mostrar la cuenta; si dice "No tokens stored", falta este paso, que solo puede hacer el propietario:

1. Crear un cliente OAuth "Desktop app" en Google Cloud Console (con las APIs de Gmail y Calendar habilitadas) y descargar `client_secret.json`.
2. `gog auth credentials <ruta al client_secret.json>`
3. `gog auth add <su-gmail> --services gmail,calendar --remote` (flujo headless: imprime una URL para autorizar desde el móvil/PC y se pega el código de vuelta).

Los tokens OAuth quedan en el keyring/home del usuario, fuera del repositorio. Rotación: revocar el acceso en la cuenta de Google y repetir `gog auth add`.

## Subida de documentos al RAG desde Telegram

La herramienta MCP `jarvis_upload` (en `integrations/openclaw/skills/jarvis-rag/server.py`) sube un archivo a `POST /v1/documents`. OpenClaw deja los adjuntos de Telegram en `media/inbound/` del workspace y el agente pasa esa ruta a la herramienta. Protecciones: allowlist de directorios de origen (media del workspace, `~/jarvis-inbox`, `/srv/jarvis/documents`), extensiones soportadas por el RAG, y límite de 50 MiB; la API además valida MIME real, tamaño y duplicados por SHA-256. Verificado end-to-end (criterios 11-14 de aceptación): subida → indexación (5 chunks) → respuesta citando documento y sección → rechazo sin evidencia.

## Watchdog proactivo

`scripts/jarvis-watchdog` + timer systemd de usuario (cada 5 min, unidades en `infra/systemd/`): comprueba `jarvis-api`, `jarvis-worker`, `ollama`, `openclaw-gateway`, salud de los contenedores (Postgres, Redis, Qdrant), `GET /ready`, disco ≥90% y GPU. Avisa por Telegram usando la API del bot directamente (sin pasar por el LLM) y **solo cuando el estado cambia** (avería o recuperación), guardando el último estado en `~/.local/state/jarvis-watchdog.state`.

## Instalación reproducible

* `scripts/install-openclaw`: npm global, plugin SearXNG, whisper.cpp + modelo, Piper + voz es_ES, wrapper TTS, workspace, daemon systemd con linger y watchdog. Idempotente (verificado en segunda ejecución).
* `scripts/configure-telegram`: guarda el token del bot en `~/.openclaw/secrets/` (fuera de Git), genera `openclaw.json` desde `integrations/openclaw/config/openclaw.template.json` (plantilla sin secretos), aplica la política de exec approvals con su allowlist y reinicia el gateway.

## Guía de bienvenida en /new y /reset

Hook interno gestionado `nueva-sesion-ayuda` (`~/.openclaw/hooks/`, fuente en `integrations/openclaw/hooks/`): al ejecutar `/new` o `/reset`, empuja un mensaje largo con todas las herramientas, usos y comandos disponibles (`event.messages.push`), que Telegram entrega junto al aviso de sesión nueva. El handler debe ser `.js` (el loader de hooks gestionados no acepta `.ts`). Se habilita con `openclaw hooks enable nueva-sesion-ayuda`; nota: al activar hooks internos, el gateway también carga los hooks bundled (p. ej. `session-memory`, que guarda contexto de sesión en `memory/` al hacer `/new`).

## Daemon

Instalado como servicio de usuario systemd (`~/.config/systemd/user/openclaw-gateway.service`, generado por `openclaw gateway install`), con `loginctl enable-linger jarvis` para que sobreviva a un reinicio sin sesión interactiva abierta. Escucha únicamente en `127.0.0.1:18789` (websocket del gateway).

## Verificación de red

```bash
ss -tlnp | grep 18789
# LISTEN 127.0.0.1:18789 y [::1]:18789 únicamente
```
