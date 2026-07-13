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

**Pendiente**: `/upload` (adjuntar documentos desde Telegram) y `/cancel` de trabajos concretos aún no están conectados a la skill; `/jobs` y la cancelación por API sí funcionan vía `jarvis_jobs`/`jarvis_cancel_job`.

## Seguridad

* Sin webhook público: long polling gestionado por el propio proceso de OpenClaw.
* Sin ejecución de shell: `tools.deny` bloquea `exec`/`process`/`code_execution`/`browser` a nivel global (ver `docs/OPENCLAW.md`); la única superficie de acción es la skill `jarvis-rag`.
* Cada mensaje de Telegram se trata como entrada no confiable (igual que cada documento del RAG): el `system prompt` de `HybridRagOrchestrator` delimita el contexto recuperado y prohíbe ejecutar instrucciones contenidas en él.

## Incidencia conocida de esta fase

Al arrancar el gateway por primera vez, `openclaw doctor`/`gateway install` ejecutó una batería de mensajes de diagnóstico internos (`channel=webchat`) contra la sesión `agent:main:main`, la misma que usa la conversación real de Telegram. Esto saturó el contexto de esa sesión (`Context overflow: prompt too large for the model`) y provocó errores en los primeros mensajes reales del usuario. Solución aplicada: `/new` en Telegram para abrir una sesión limpia. Pendiente de confirmar en la revisión de mañana si conviene además purgar `~/.openclaw/agents/main/sessions/` tras cada `doctor`/`gateway install`.
