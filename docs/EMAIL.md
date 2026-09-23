# Correo (Fase 3 del roadmap)

MCP de correo: leer la bandeja de entrada, leer un mensaje como entrada no confiable,
y redactar+confirmar el envío, con documentos generados adjuntos. **Nunca envía nada
de forma autónoma**: todo envío pasa por borrador → confirmación explícita del
propietario en Telegram → envío.

## Proveedores

Se elige con `MAIL_PROVIDER` en `.env`:

| `MAIL_PROVIDER` | Implementación | Cuentas | Requisitos |
|---|---|---|---|
| `imap` (por defecto) | `packages/imapsmtp/mail.py`: IMAP para leer, SMTP para enviar (biblioteca estándar) | Cualquier proveedor con IMAP/SMTP: Gmail/Google Workspace, iCloud, Fastmail, Zoho, Nextcloud Mail, Proton Bridge, servidor propio | Una **contraseña de aplicación** de la cuenta. Nada que registrar en Azure ni en Google Cloud |
| `msgraph` | `packages/msgraph/mail.py` | Microsoft 365 / Outlook | Registro de app en Azure AD y login por código de dispositivo (`docs/MSGRAPH.md`) |

`imap` es el valor por defecto porque cualquiera puede usarlo sin ser administrador de
un tenant. Los dos backends devuelven los mensajes con la misma forma (la de Graph), así
que el router y el servidor MCP no cambian según el proveedor.

### Configurar IMAP/SMTP

```bash
scripts/configure-mail
```

Pregunta el proveedor (Gmail, iCloud, Fastmail u otro), la dirección y la contraseña de
aplicación y, opcionalmente, la URL CalDAV del calendario (`docs/CALENDAR.md`). Escribe
las variables en `.env`, prueba IMAP y el login SMTP **sin enviar nada** y recrea el
contenedor `api` para que cargue la configuración.

Contraseñas de aplicación:

* **Gmail**: requiere la verificación en dos pasos; se crean en
  <https://myaccount.google.com/apppasswords>.
* **iCloud**: <https://account.apple.com> → Inicio de sesión y seguridad → Contraseñas
  específicas de apps.
* **Fastmail**: Ajustes → Privacidad y seguridad → Contraseñas de aplicaciones.
* **Outlook.com / Hotmail**: Microsoft ya no acepta contraseñas en IMAP/SMTP para
  cuentas personales (solo OAuth2), así que con `imap` lo más probable es que el login
  falle. Usa otra cuenta para Jarvis: puede enviar correos a cualquier dirección,
  incluidas las de Outlook.

Recomendación: una cuenta dedicada para Jarvis, no tu buzón personal.

Variables (ver `.env.example`): `MAIL_PROVIDER`, `IMAP_HOST`, `IMAP_PORT` (993, TLS
implícito), `IMAP_MAILBOX` (`INBOX`), `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`
(`starttls` en 587, `ssl` en 465), `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` (vacío =
`MAIL_USERNAME`). Si falta alguna, la API responde `provider_unavailable` nombrando las
que faltan, y el agente se lo dice al usuario.

La lectura por IMAP abre el buzón en solo lectura (`EXAMINE` + `BODY.PEEK[]`): listar o
leer no marca nada como leído. Los identificadores de mensaje son UIDs IMAP.

## Qué hay aquí

* `packages/imapsmtp/mail.py` — `list_inbox`, `get_message`, `send_mail` y
  `check_smtp_login` sobre IMAP/SMTP.
* `packages/msgraph/mail.py` — `list_inbox`, `get_message`, `send_mail` sobre
  `MsGraphClient` (`GET /me/mailFolders/inbox/messages`, `GET /me/messages/{id}`,
  `POST /me/sendMail`).
* `apps/api/jarvis_api/adapters/mail_backends.py` — protocolo `MailBackend` y selección
  del backend según `MAIL_PROVIDER`.
* `apps/api/jarvis_api/routers/email.py` (`/v1/email`) — API interna, protegida como el
  resto (`require_internal_token`):
  * `GET /messages?top=N` — lista la bandeja (máx. 50).
  * `GET /messages/{id}` — lee un mensaje; su `body.content` se devuelve envuelto
    entre `<correo_no_confiable>...</correo_no_confiable>`, el mismo convenio de
    delimitar entrada no confiable que usa el RAG con `<contexto>` (ver
    `docs/SECURITY.md`).
  * `POST /draft` — valida destinatarios y el adjunto (si lo hay), crea una
    `PendingConfirmation` vía `ConfirmationService.request(..., payload=...)`, manda
    al propietario por Telegram el correo completo con los botones Enviar/Descartar y
    devuelve solo el resumen (sin token). No envía nada todavía.
  * `POST /draft/{token}/confirm` — confirma el token (caduca a los
    `CONFIRMATION_TTL_SECONDS` configurados, un solo uso, ligado al
    `telegram_user_id` que lo pidió) y solo entonces envía. Lo llama el plugin
    `jarvis-aprobaciones` al pulsar Enviar, con el ID de quien pulsa.
  * `POST /draft/{token}/cancel` — lo mismo con Descartar: borra el borrador.
* `integrations/openclaw/skills/jarvis-email/` — servidor MCP (`FastMCP`) con
  tres herramientas: `jarvis_email_inbox`, `jarvis_email_read` y
  `jarvis_email_draft`. Ninguna envía: el envío solo lo hace el botón. Un servidor MCP por
  capacidad, igual que `jarvis-rag`: no se añade a `jarvis-rag`, es un sibling.

## Correo y OpenProject

Con el perfil `pm`, OpenProject usa esta misma cuenta para enviar sus correos (avisos e
invitaciones a reuniones, `docs/OPENPROJECT.md`), y `jarvis-pm` puede convertir un correo
de la bandeja en una tarea (`pm_task_from_email`: el texto se copia como descripción, sin
obedecer lo que diga). Con `CALENDAR_PROVIDER=openproject`, los invitados que no son
usuarios de OpenProject reciben la invitación (.ics) desde esta cuenta.

## Adjuntar documentos generados

`jarvis_email_draft(..., attachment_job_id="<id>")` adjunta el documento de un trabajo de
doc-gen terminado (`docs/DOCGEN.md`), p. ej. "resúmeme el PMBOK en PDF y mándamelo por
correo". La API lo lee del volumen de datos al confirmar el envío, y el resumen del
borrador muestra el nombre del adjunto para que el propietario vea qué se envía. Con
`msgraph` el adjunto va inline en `sendMail`, que Graph limita a 3 MB.

## Flujo de confirmación

Reutiliza exactamente el mismo mecanismo que el resto de acciones sensibles del
proyecto (`packages/security/confirmation.py`, `CONFIRMATION_TTL_SECONDS`): el
borrador se guarda en Redis con un token de un solo uso y expiración; solo el mismo
`telegram_user_id` que pidió el borrador puede confirmarlo, y una vez confirmado (o
caducado) el token se borra. El TTL por defecto es de 10 minutos: con un modelo local
grande cada turno del agente tarda del orden de un minuto, y con 2 minutos los "sí" del
propietario llegaban cuando el token ya había caducado.

La aprobación no pasa por el modelo. La API manda el borrador por Telegram (texto plano,
tal cual se enviará) con dos botones cuyo callback lleva el token
(`correo:enviar:<token>`, `correo:descartar:<token>`), y el plugin de OpenClaw
`jarvis-aprobaciones` (`integrations/openclaw/plugins/jarvis-aprobaciones`) confirma
contra la API con el ID de Telegram de quien pulsa. El agente nunca ve el token ni tiene
herramienta para confirmar, así que un correo o documento con instrucciones maliciosas no
puede conseguir que envíe nada, aunque le convenza de que el propietario dijo "sí".

Sin `TELEGRAM_BOT_TOKEN` no se pueden aprobar correos: `POST /draft` responde con error y
no guarda el borrador.

## Entrada no confiable

El cuerpo de un correo puede contener instrucciones maliciosas (prompt injection).
Se trata igual que el contenido de documentos RAG o mensajes de Telegram (ver
`docs/SECURITY.md`): se delimita explícitamente
(`<correo_no_confiable>...</correo_no_confiable>`) y la herramienta MCP
`jarvis_email_read` añade además un aviso textual explícito. Nunca se ejecutan
instrucciones contenidas en un correo.

## Activación

`jarvis-email` ya está en `mcp.servers` y `jarvis-email__*` en
`tools.sandbox.tools.alsoAllow` de la plantilla
`integrations/openclaw/config/openclaw.template.json`; `scripts/configure-telegram`
rellena `JARVIS_OWNER_TELEGRAM_ID`. Solo falta configurar la cuenta
(`scripts/configure-mail`).
