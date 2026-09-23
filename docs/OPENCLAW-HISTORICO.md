# OpenClaw — instalación sin Docker e historial

Este documento recoge lo que ya **no** describe el despliegue actual: la instalación
original con npm y systemd de usuario (que sigue siendo válida en un servidor sin
Docker), la integración de correo y calendario con `gog` —sustituida por IMAP/SMTP y
CalDAV/OpenProject, ver `docs/EMAIL.md` y `docs/CALENDAR.md`—, y los incidentes de
julio y septiembre de 2026 con sus mediciones. Para el despliegue vigente, ver
`docs/OPENCLAW.md`.

> Las secciones de este documento hablan de una GTX 1070 de 8 GB, del usuario `jarvis`
> del servidor original y de modelos (`qwen2.5:7b`, `qwen3:4b`) que ya no son los del
> despliegue actual. Se conservan porque justifican decisiones que siguen vigentes: el
> prompt corto, las herramientas de orquestación denegadas y la ventana de contexto de
> Ollama.

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
