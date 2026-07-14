# Telegram — integración

Un único bot, administrado íntegramente por OpenClaw (long polling, sin webhooks públicos).

## Bot

* Bot creado por el usuario vía `@BotFather` (`/newbot`). Nombre: **Jarvis-UE**, usuario `@RomenAdamaDev_bot`.
* Token guardado fuera del repositorio en `~/.openclaw/secrets/telegram_bot_token` (permisos `600`), referenciado desde `openclaw.json` mediante `channels.telegram.tokenFile` (nunca como valor literal en config ni en git).

## Autorización

* `channels.telegram.dmPolicy: "allowlist"` + `channels.telegram.allowFrom: ["<telegram_user_id>"]`: solo ese ID numérico puede conversar con el bot: cualquier otro remitente es rechazado antes de llegar al agente.
* `commands.ownerAllowFrom: ["telegram:<telegram_user_id>"]`: separa "quién puede hablar con el bot" (`allowFrom`) de "quién es el operador con privilegios" (`ownerAllowFrom`) para comandos como `/diagnostics` o aprobaciones de acciones sensibles.
* El ID numérico se obtuvo emparejando primero con `dmPolicy: "pairing"` (el bot entrega un código de un solo uso al remitente desconocido y lo muestra en su propia respuesta de Telegram), y una vez confirmado el ID se fijó `dmPolicy` en `allowlist` con ese valor explícito como configuración final (más simple de auditar que dejar el emparejamiento como mecanismo permanente).

## Comandos

Los comandos base (`/status`, `/new`, `/reset`, `/think`, etc.) son nativos de OpenClaw. Los específicos de Jarvis (`/ask`, `/deep`, `/sources`, `/models`, `/disk`, `/jobs`) se resuelven mediante lenguaje natural invocando las herramientas MCP de la skill `jarvis-rag` (ver `docs/OPENCLAW.md`): no son comandos de barra registrados aparte, la skill instruye al agente para usarlas ante la intención correspondiente.

`/deep` es asíncrono por diseño (criterio 17): `jarvis_deep` encola un trabajo y responde al momento con su identificador, el worker ejecuta la consulta contra AirLLM sin bloquear al bot, y la respuesta se recoge con `jarvis_job_result` (o se lista con `/jobs`). Ver `docs/AIRLLM.md`.

**Pendiente**: `/upload` (adjuntar documentos desde Telegram) y `/cancel` de trabajos concretos aún no están conectados a la skill; `/jobs` y la cancelación por API sí funcionan vía `jarvis_jobs`/`jarvis_cancel_job`.

## Seguridad

* Sin webhook público: long polling gestionado por el propio proceso de OpenClaw.
* Sin ejecución de shell: `tools.deny` bloquea `exec`/`process`/`code_execution`/`browser` a nivel global (ver `docs/OPENCLAW.md`); la única superficie de acción es la skill `jarvis-rag`.
* Cada mensaje de Telegram se trata como entrada no confiable (igual que cada documento del RAG): el `system prompt` de `HybridRagOrchestrator` delimita el contexto recuperado y prohíbe ejecutar instrucciones contenidas en él.

## Incidencias resueltas durante la puesta en marcha

Las tres se manifestaban igual para el usuario ("Something went wrong" o respuestas incoherentes), pero tenían causas distintas:

1. **Sandbox Docker inexistente**: con `agents.defaults.sandbox.mode: "non-main"`, cada sesión de Telegram intentaba arrancar en la imagen `openclaw-sandbox:bookworm-slim`, que no está construida en este host (`Embedded agent failed before reply: Sandbox image not found`). Solución: `sandbox.mode: "off"` (justificación en `docs/OPENCLAW.md`).
2. **Truncado silencioso por contexto de Ollama**: Ollama sirve por defecto con `num_ctx=4096`, pero el prompt de sistema de OpenClaw (herramientas + workspace + menú de comandos) ronda los 14k tokens. Ollama truncaba el prompt sin avisar y el modelo, viendo un prompt cortado, respondía texto incoherente y llamadas a herramientas en JSON crudo. Solución: `OLLAMA_CONTEXT_LENGTH=32768` en el override de systemd de Ollama (reflejado en `scripts/install-ollama`) y `contextWindow: 32768` en los modelos de `openclaw.json`. Nota: OpenClaw reserva ~20k tokens sobre la ventana declarada, así que una ventana de 16k deja presupuesto negativo — no usar valores intermedios sin comprobar ese margen. Coste en VRAM medido: qwen2.5:7b pasa de 4.7 a 6.4 GB con el KV cache de 32k, sigue al 100% en GPU (8 GB).
3. **Sesión contaminada por diagnósticos**: los primeros arranques (`doctor`, batería `webchat`) llenaron la sesión `agent:main:main` de mensajes internos, dejándola en desbordamiento permanente incluso tras arreglar lo anterior. Solución: `/new` desde Telegram (o `openclaw agent --agent main --message "/new"`) tras cualquier cambio de configuración mayor.

Verificación final: `openclaw agent --agent main --message "..."` responde coherente en español, `ollama ps` muestra `100% GPU` con `CONTEXT 32768` durante la respuesta, y el bot envía y recibe por Telegram.
