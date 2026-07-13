# OpenClaw — integración

## Instalación

OpenClaw (`openclaw/openclaw`, licencia MIT) se instala solo para el usuario humano de desarrollo (`jarvis`, uid 1000), nunca para `jarvis-svc`: es el plano de control personal desde el móvil, no un servicio de la plataforma.

```bash
npm config set prefix ~/.npm-global
npm install -g openclaw@latest
export PATH=~/.npm-global/bin:$PATH   # añadido a ~/.bashrc
```

Requiere Node.js 22.19+ (Ubuntu 26.04 trae 22.22.1 en sus repos oficiales, sin añadir NodeSource).

## Configuración

Archivo: `~/.openclaw/openclaw.json` (JSON5/JSON, permisos `600`, fuera del repositorio — nunca se versiona porque contiene el token de Telegram y el token interno de Jarvis API).

Decisiones clave:

* **Modelo**: proveedor `custom` apuntando directamente al endpoint OpenAI-compatible de Ollama (`http://127.0.0.1:11434/v1`), con los dos modelos seleccionados en `docs/BENCHMARKS.md` (`qwen2.5:7b-instruct-q4_K_M` rápido por defecto, `llama3.1:8b-instruct-q4_K_M` potente disponible). Ollama y Jarvis API ya cumplen "proveedor local" exigido por el prompt; no fue necesario levantar un endpoint OpenAI-compatible adicional en Jarvis API para esto.
* **`agents.defaults.memorySearch.enabled: false`**: por defecto OpenClaw usa OpenAI para búsqueda semántica de memoria. Se desactiva explícitamente para no violar el principio "sin fallback a proveedores externos".
* **Sandbox**: `agents.defaults.sandbox.mode: "off"`. Se probó `"non-main"` (sandbox Docker para sesiones no principales) pero el host no soporta el aislamiento por namespaces que requiere (`bwrap: setting up uid map: Permission denied`, ver aviso de `openclaw doctor`), y con un único usuario autorizado no hay sesiones "no principales" reales que proteger. Si en el futuro se añaden más agentes/canales, revisar esta decisión.
* **`tools.deny`**: se deniega explícitamente `exec, process, code_execution, browser, cron, nodes, gateway, image_generate, music_generate, video_generate, tts`. Esto es lo que garantiza "no ejecución de shell arbitraria desde Telegram": el agente no tiene ninguna vía de shell, solo las herramientas MCP explícitas de `jarvis-rag`.
* **`tools.sandbox.tools.alsoAllow: ["jarvis-rag__*"]`**: necesario para que las herramientas del servidor MCP sigan siendo visibles si en el futuro se reactiva el sandbox.
* **`gateway.auth`**: token generado automáticamente por `openclaw doctor --fix` (websocket del gateway protegido incluso en loopback).

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

## Subida de documentos al RAG desde Telegram

La herramienta MCP `jarvis_upload` (en `integrations/openclaw/skills/jarvis-rag/server.py`) sube un archivo a `POST /v1/documents`. OpenClaw deja los adjuntos de Telegram en `media/inbound/` del workspace y el agente pasa esa ruta a la herramienta. Protecciones: allowlist de directorios de origen (media del workspace, `~/jarvis-inbox`, `/srv/jarvis/documents`), extensiones soportadas por el RAG, y límite de 50 MiB; la API además valida MIME real, tamaño y duplicados por SHA-256. Verificado end-to-end (criterios 11-14 de aceptación): subida → indexación (5 chunks) → respuesta citando documento y sección → rechazo sin evidencia.

## Watchdog proactivo

`scripts/jarvis-watchdog` + timer systemd de usuario (cada 5 min, unidades en `infra/systemd/`): comprueba `jarvis-api`, `jarvis-worker`, `ollama`, `openclaw-gateway`, salud de los contenedores (Postgres, Redis, Qdrant), `GET /ready`, disco ≥90% y GPU. Avisa por Telegram usando la API del bot directamente (sin pasar por el LLM) y **solo cuando el estado cambia** (avería o recuperación), guardando el último estado en `~/.local/state/jarvis-watchdog.state`.

## Instalación reproducible

* `scripts/install-openclaw`: npm global, plugin SearXNG, whisper.cpp + modelo, Piper + voz es_ES, wrapper TTS, workspace, daemon systemd con linger y watchdog. Idempotente (verificado en segunda ejecución).
* `scripts/configure-telegram`: guarda el token del bot en `~/.openclaw/secrets/` (fuera de Git), genera `openclaw.json` desde `integrations/openclaw/config/openclaw.template.json` (plantilla sin secretos), aplica la política de exec approvals con su allowlist y reinicia el gateway.

## Daemon

Instalado como servicio de usuario systemd (`~/.config/systemd/user/openclaw-gateway.service`, generado por `openclaw gateway install`), con `loginctl enable-linger jarvis` para que sobreviva a un reinicio sin sesión interactiva abierta. Escucha únicamente en `127.0.0.1:18789` (websocket del gateway).

## Verificación de red

```bash
ss -tlnp | grep 18789
# LISTEN 127.0.0.1:18789 y [::1]:18789 únicamente
```
