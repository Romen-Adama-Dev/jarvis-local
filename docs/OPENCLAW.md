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

## Daemon

Instalado como servicio de usuario systemd (`~/.config/systemd/user/openclaw-gateway.service`, generado por `openclaw gateway install`), con `loginctl enable-linger jarvis` para que sobreviva a un reinicio sin sesión interactiva abierta. Escucha únicamente en `127.0.0.1:18789` (websocket del gateway).

## Verificación de red

```bash
ss -tlnp | grep 18789
# LISTEN 127.0.0.1:18789 y [::1]:18789 únicamente
```
