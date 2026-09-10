# Calendario (Microsoft Graph)

Fase 4 del roadmap (`docs/ROADMAP.md`): consultar disponibilidad y proponer/crear
eventos en el calendario de Outlook/Microsoft 365 del propietario. Construida sobre
`feature/mcp-msgraph-base` (`packages/msgraph/`, ver `docs/MSGRAPH.md`): ejecuta
primero `scripts/configure-msgraph` para tener una sesión de Graph válida antes de
usar nada de aquí.

**Nunca crea eventos de forma autónoma.** El flujo es siempre "proponer, luego
confirmar", reutilizando `packages/security/confirmation.py`
(`ConfirmationService`, con TTL corto vía `CONFIRMATION_TTL_SECONDS`) — el mismo
patrón que correo (`feature/mcp-email`) y que la regla de escritura de `gog`
descrita en `docs/OPENCLAW.md`.

## Scopes de Graph necesarios

`Calendars.Read` y `Calendars.ReadWrite`, ya listados en el registro de la app de
Azure AD documentado en `docs/MSGRAPH.md` (junto a los de correo). No hace falta
nada adicional en Azure para esta capacidad.

## Qué hay aquí

* `packages/msgraph/calendar.py` — `get_calendar_view(client, start, end)` (lee
  `/me/calendarview`) y `create_event(client, subject, start, end, attendees,
  body, timezone)` (crea vía `POST /me/events`), ambas funciones planas sobre un
  `MsGraphClient` ya autenticado.
* `apps/api/jarvis_api/routers/calendar.py` (`/v1/calendar`, requiere el token
  interno como el resto de la API):
  - `GET /events?start=...&end=...` — solo lectura, sin confirmación.
  - `POST /draft` — valida los campos mínimos y registra una
    `PendingConfirmation` con el payload completo del evento propuesto
    (`ConfirmationService.request(..., payload=...)`); devuelve `token`,
    `summary` y `expires_at`. **No crea nada todavía.**
  - `POST /draft/{token}/confirm` — consume el token (uso único, comprobando
    TTL y propietario) y entonces sí llama a `create_event`.
* `integrations/openclaw/skills/jarvis-calendar/` — servidor MCP con tres
  herramientas: `jarvis_calendar_availability` (lectura),
  `jarvis_calendar_propose_event` (llama a `POST /draft`) y
  `jarvis_calendar_confirm_event` (llama a `POST /draft/{token}/confirm`).

## Aviso: confirmar con invitados envía invitaciones reales

Si la propuesta incluye `attendees`, confirmarla (`jarvis_calendar_confirm_event`)
hace que Microsoft Graph envíe invitaciones de verdad a esas direcciones — no hay
forma de deshacerlo desde Jarvis. El `SKILL.md` de `jarvis-calendar` deja explícito
que el agente solo debe llamar a `jarvis_calendar_confirm_event` cuando el usuario
lo haya pedido explícitamente para esa propuesta concreta, igual que la regla ya
existente para `gog` en `docs/OPENCLAW.md`.

## Pendiente / fuera de esta rama

* Editar o cancelar eventos existentes (`PATCH`/`DELETE /me/events/{id}`): no
  hay herramienta MCP para ello todavía, solo creación.
* Recordatorios o disponibilidad agregada (`/me/findMeetingTimes`): no
  implementado, `jarvis_calendar_availability` solo lista eventos existentes en
  el rango pedido.
