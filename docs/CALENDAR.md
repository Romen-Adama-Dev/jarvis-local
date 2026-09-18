# Calendario (Fase 4 del roadmap)

Consultar disponibilidad y proponer/crear eventos en el calendario del propietario.

**Nunca crea eventos de forma autónoma.** El flujo es siempre "proponer, luego
confirmar", reutilizando `packages/security/confirmation.py`
(`ConfirmationService`, con TTL vía `CONFIRMATION_TTL_SECONDS`) — el mismo patrón que
el correo (`docs/EMAIL.md`).

## Proveedores

Se elige con `CALENDAR_PROVIDER` en `.env`:

| `CALENDAR_PROVIDER` | Implementación | Cuentas | Requisitos |
|---|---|---|---|
| `caldav` (por defecto) | `packages/caldavcal/calendar.py` (biblioteca `caldav`) | Nextcloud, iCloud, Fastmail, Radicale, SOGo, Baïkal, Zimbra... | URL CalDAV + usuario y contraseña de aplicación |
| `openproject` | `packages/openproject/calendar.py` | Las reuniones de OpenProject (perfil `pm`) | Nada más: usa la clave de API de Jarvis que genera `init` |
| `msgraph` | `packages/msgraph/calendar.py` | Microsoft 365 / Outlook | Registro de app en Azure AD (`docs/MSGRAPH.md`), scopes `Calendars.Read` y `Calendars.ReadWrite` |

Google Calendar no admite CalDAV con contraseña de aplicación (solo OAuth2): con una
cuenta de Gmail, usa `openproject` (las invitaciones llegan igualmente a Google Calendar,
ver abajo) u otro proveedor.

### OpenProject como calendario (`CALENDAR_PROVIDER=openproject`)

Con el perfil `pm` activo, la agenda de Jarvis son las **reuniones de OpenProject**: las
que se crean desde Telegram, desde la web o al importar un acta. Así reuniones, tareas y
actas viven en el mismo sitio.

* **Consultar** (`jarvis_calendar_availability`): reuniones de todos los proyectos en el
  rango y, como avisos de día completo ("Vence #id"), las tareas e hitos abiertos que
  vencen esos días. Cada línea lleva el enlace a OpenProject por Tailscale.
* **Crear** (`jarvis_calendar_propose_event` → confirmación): la reunión va al proyecto
  que se nombre (`project`) o, si no, al proyecto `Agenda` (se crea solo; nombre en
  `OPENPROJECT_CALENDAR_PROJECT`). `location` admite sala o enlace de videollamada y
  `body` queda como punto del orden del día.
* **Invitados**: los que son usuarios de OpenProject entran como participantes y
  OpenProject les manda la invitación con el .ics; el resto recibe un correo con la
  invitación (.ics, `METHOD:REQUEST`) desde la cuenta de Jarvis. El propietario (usuario
  `admin`) participa siempre.
* **En tu móvil**: el admin tiene el correo de Jarvis (o `OPENPROJECT_ADMIN_MAIL`), así
  que cada invitación llega a ese buzón y Gmail la añade a Google Calendar (y de ahí al
  calendario del iPhone si tienes la cuenta de Google en él). Alternativa sin correo:
  en OpenProject, **Reuniones → Suscribirse al calendario**, copia la URL `.ics` y
  añádela en el iPhone en Ajustes → Calendario → Cuentas → Añadir cuenta → Otra →
  Añadir calendario suscrito (necesita Tailscale conectado para actualizarse).

### Configurar CalDAV

`scripts/configure-mail` pregunta también la URL CalDAV (propone la de iCloud y la de
Fastmail) y prueba la conexión leyendo los próximos 7 días. URLs habituales:

* iCloud: `https://caldav.icloud.com/`
* Fastmail: `https://caldav.fastmail.com/dav/`
* Nextcloud: `https://<servidor>/remote.php/dav/`
* Radicale: `http://<servidor>:5232/`

Variables (ver `.env.example`): `CALENDAR_PROVIDER`, `CALDAV_URL`,
`CALDAV_USERNAME`/`CALDAV_PASSWORD` (vacías = las del correo), `CALDAV_CALENDAR_NAME`
(nombre visible; vacío = el primero de la cuenta) y `CALENDAR_TIMEZONE`
(`Europe/Madrid`: zona en la que se interpretan las fechas sin zona horaria que manda el
agente). Sin `CALDAV_URL`, la API responde `provider_unavailable` y el agente se lo dice
al usuario.

`get_calendar_view` expande las recurrencias dentro del rango pedido; `create_event`
guarda un `VEVENT` con su `VTIMEZONE`, el organizador (si el usuario es una dirección de
correo) y los invitados como `ATTENDEE` con `RSVP=TRUE`.

## Qué hay aquí

* `packages/caldavcal/calendar.py` — `get_calendar_view(config, start, end)` y
  `create_event(config, subject, start, end, attendees, body)` sobre CalDAV.
* `packages/msgraph/calendar.py` — `get_calendar_view(client, start, end)` (lee
  `/me/calendarview`) y `create_event(client, subject, start, end, attendees,
  body, timezone)` (crea vía `POST /me/events`).
* `apps/api/jarvis_api/adapters/calendar_backends.py` — protocolo `CalendarBackend` y
  selección del backend según `CALENDAR_PROVIDER`.
* `apps/api/jarvis_api/routers/calendar.py` (`/v1/calendar`, requiere el token
  interno como el resto de la API):
  - `GET /events?start=...&end=...` — solo lectura, sin confirmación.
  - `POST /draft` — valida los campos mínimos y registra una
    `PendingConfirmation` con el payload completo del evento propuesto
    (`ConfirmationService.request(..., payload=...)`); devuelve `token`,
    `summary` y `expires_at`. **No crea nada todavía.**
  - `POST /draft/{token}/confirm` — consume el token (uso único, comprobando
    TTL y propietario) y entonces sí crea el evento.
* `integrations/openclaw/skills/jarvis-calendar/` — servidor MCP con tres
  herramientas: `jarvis_calendar_availability` (lectura),
  `jarvis_calendar_propose_event` (llama a `POST /draft`) y
  `jarvis_calendar_confirm_event` (llama a `POST /draft/{token}/confirm`).

## Aviso: confirmar con invitados envía invitaciones reales

Si la propuesta incluye `attendees`, confirmarla puede enviar invitaciones de verdad:
con `msgraph` las envía siempre Microsoft Graph; con `caldav` depende del servidor (los
que implementan planificación implícita, como iCloud, Fastmail o Nextcloud, las envían
al guardar el evento; Radicale solo lo guarda). No hay forma de deshacerlo desde Jarvis.
El `SKILL.md` de `jarvis-calendar` deja explícito que el agente solo debe llamar a
`jarvis_calendar_confirm_event` cuando el usuario lo haya pedido explícitamente para esa
propuesta concreta.

## Pendiente

* Con `openproject`: mover o cancelar reuniones y reuniones recurrentes se hacen desde la
  web por ahora.

* Editar o cancelar eventos existentes: no hay herramienta MCP para ello todavía,
  solo creación.
* Recordatorios o disponibilidad agregada (búsqueda de huecos comunes): no
  implementado, `jarvis_calendar_availability` solo lista eventos existentes en
  el rango pedido.
