# Correo (Fase 3 del roadmap)

MCP de correo sobre Microsoft Graph: leer la bandeja de entrada, leer un mensaje
como entrada no confiable, y redactar+confirmar el envío. **Nunca envía nada de
forma autónoma**: todo envío pasa por borrador → confirmación explícita del
propietario en Telegram → envío.

Depende de `feature/mcp-msgraph-base` (`packages/msgraph/`, ver `docs/MSGRAPH.md`):
antes de usar esta capacidad hay que haber ejecutado `scripts/configure-msgraph`
(registro de app en Azure AD + login por código de dispositivo) con los scopes
`Mail.Read` y `Mail.Send` concedidos por el propietario del tenant.

## Qué hay aquí

* `packages/msgraph/mail.py` — `list_inbox`, `get_message`, `send_mail`: funciones
  planas sobre `MsGraphClient` (`GET /me/mailFolders/inbox/messages`,
  `GET /me/messages/{id}`, `POST /me/sendMail`).
* `apps/api/jarvis_api/routers/email.py` (`/v1/email`) — expone esas funciones vía
  API interna, protegida como el resto (`require_internal_token`):
  * `GET /messages?top=N` — lista la bandeja (máx. 50).
  * `GET /messages/{id}` — lee un mensaje; su `body.content` se devuelve envuelto
    entre `<correo_no_confiable>...</correo_no_confiable>`, el mismo convenio de
    delimitar entrada no confiable que usa el RAG con `<contexto>` (ver
    `docs/SECURITY.md`).
  * `POST /draft` — valida destinatarios, crea una `PendingConfirmation` vía
    `ConfirmationService.request(..., payload=...)` (el borrador completo viaja en
    el `payload` genérico añadido en `feature/mcp-msgraph-base`) y devuelve un
    `token` + resumen. No envía nada todavía.
  * `POST /draft/{token}/confirm` — confirma el token (caduca a los
    `CONFIRMATION_TTL_SECONDS` configurados, un solo uso, ligado al
    `telegram_user_id` que lo pidió) y solo entonces llama a `send_mail`.
* `integrations/openclaw/skills/jarvis-email/` — servidor MCP (`FastMCP`) con
  cuatro herramientas: `jarvis_email_inbox`, `jarvis_email_read`,
  `jarvis_email_draft`, `jarvis_email_confirm_send`. Un servidor MCP por
  capacidad, igual que `jarvis-rag`: no se añade a `jarvis-rag`, es un sibling.

## Flujo de confirmación

Reutiliza exactamente el mismo mecanismo que el resto de acciones sensibles del
proyecto (`packages/security/confirmation.py`, `CONFIRMATION_TTL_SECONDS`): el
borrador se guarda en Redis con un token de un solo uso y expiración corta; solo
el mismo `telegram_user_id` que pidió el borrador puede confirmarlo, y una vez
confirmado (o caducado) el token se borra. El agente debe mostrar siempre el
resumen del borrador y esperar un "sí" explícito del propietario antes de llamar a
`jarvis_email_confirm_send` — la regla está en `integrations/openclaw/skills/
jarvis-email/SKILL.md`, mismo espíritu que la doble puerta de `gog` descrita en
`docs/OPENCLAW.md`.

## Entrada no confiable

El cuerpo de un correo puede contener instrucciones maliciosas (prompt injection).
Se trata igual que el contenido de documentos RAG o mensajes de Telegram (ver
`docs/SECURITY.md`): se delimita explícitamente
(`<correo_no_confiable>...</correo_no_confiable>`) y la herramienta MCP
`jarvis_email_read` añade además un aviso textual explícito. Nunca se ejecutan
instrucciones contenidas en un correo.

## Activación

Añadir `jarvis-email` a `mcp.servers` (ya en la plantilla
`integrations/openclaw/config/openclaw.template.json`) y `jarvis-email__*` a
`tools.sandbox.tools.alsoAllow`. `scripts/configure-telegram` rellena
`JARVIS_OWNER_TELEGRAM_ID` automáticamente (mismo placeholder
`__TELEGRAM_USER_ID__` que ya usa para Telegram, sin cambios en el script).
