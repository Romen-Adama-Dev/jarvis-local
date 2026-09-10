# Microsoft Graph — base compartida (correo y calendario)

Esta rama (`feature/mcp-msgraph-base`) construye únicamente la base común que
necesitarán tanto el correo (Fase 3 del roadmap) como el calendario (Fase 4):
autenticación OAuth2 contra Microsoft Graph y un cliente HTTP genérico. **No
expone ninguna herramienta MCP ni lógica de correo/calendario todavía** — eso
llega en `docs/EMAIL.md` y `docs/CALENDAR.md`, en ramas separadas
(`feature/mcp-email`, `feature/mcp-calendar`) construidas encima de esta.

Mismo principio que con Teams (`docs/TEAMS.md`) y `gog` (Google, ver el
apartado "Correo y calendario (gog)" de `docs/OPENCLAW.md`): la inferencia
del LLM sigue siendo 100% local (Ollama/AirLLM); solo los datos de
correo/calendario van y vienen de la nube de Microsoft, algo que el
propietario ya acepta al usar Microsoft 365/Teams.

## Qué hay aquí

* `packages/msgraph/auth.py` — `MsGraphTokenStore` (persiste la caché de
  tokens de MSAL en un fichero JSON fuera del repo) y `MsGraphAuthenticator`
  (obtiene un token de acceso válido desde esa caché, refrescándolo en
  silencio; si no hay sesión utilizable, lanza `ProviderUnavailableError`
  pidiendo ejecutar `scripts/configure-msgraph`). También
  `interactive_device_code_login`, la función que sí dispara el flujo de
  código de dispositivo — solo la usa el script de configuración, nunca la
  API ni el worker.
* `packages/msgraph/client.py` — `MsGraphClient`, un envoltorio async mínimo
  sobre `httpx.AsyncClient` contra `https://graph.microsoft.com/v1.0`, con
  `get`/`post`/`patch`/`delete` genéricos. No sabe nada de mensajes ni
  eventos: eso lo añaden las ramas de correo/calendario.
* `scripts/configure-msgraph` — paso de configuración único: guarda
  `client_id`/`tenant_id` y ejecuta el login interactivo una vez.

## Registro de la app en Azure AD (paso único del propietario)

Solo el propietario del tenant puede hacerlo, con acceso a Azure Portal /
Entra ID — igual que el registro de Azure Bot para Teams o el cliente OAuth
de Google Cloud Console para `gog`:

1. **Entra ID → App registrations → New registration**.
   - Tipo de cuenta: el que corresponda a tu tenant (single tenant es
     suficiente para un solo usuario).
   - **Redirect URI**: tipo "Public client/native (mobile & desktop)",
     valor `https://login.microsoftonline.com/common/oauth2/nativeclient`
     (el redirect URI estándar que usa MSAL para el flujo de código de
     dispositivo).
2. **Authentication** → activar **"Allow public client flows"** (imprescindible:
   sin esto el flujo de código de dispositivo falla).
3. **API permissions → Add a permission → Microsoft Graph → Delegated
   permissions**: añade `Mail.Read`, `Mail.Send`, `Calendars.Read`,
   `Calendars.ReadWrite`.
4. **Grant admin consent** para esos cuatro permisos (botón en la misma
   pantalla; en un tenant personal/de un solo usuario normalmente lo puede
   hacer el propio propietario si es administrador global).
5. Anota el **Application (client) ID** y el **Directory (tenant) ID** de la
   pantalla **Overview** del registro.

No hay `client secret` que gestionar: al ser una app "pública/nativa" (sin
backend confidencial), MSAL usa el flujo de código de dispositivo con
`PublicClientApplication`, sin secreto de cliente.

## `scripts/configure-msgraph`

```bash
scripts/configure-msgraph
```

1. Pide (o lee de env) `MSGRAPH_CLIENT_ID` y `MSGRAPH_TENANT_ID`, y los
   guarda en `~/.openclaw/secrets/msgraph.env` (permisos `600`, fuera de
   Git — mismo patrón que `~/.openclaw/secrets/msteams.env` para Teams). No
   son secretos en el sentido de una contraseña, pero son específicos de
   este host/tenant, así que tampoco van al repositorio.
2. Ejecuta `uv run python -c "..."` que llama a
   `packages.msgraph.auth.interactive_device_code_login` con los scopes
   `Mail.Read Mail.Send Calendars.Read Calendars.ReadWrite`. La consola
   muestra un código y la URL `https://microsoft.com/devicelogin`: complétalo
   desde cualquier navegador (móvil u otro PC) con la cuenta de Microsoft
   365 del propietario.
3. Al terminar, la caché de tokens de MSAL queda guardada y lista para que
   `MsGraphAuthenticator.get_token()` la reutilice en silencio (refrescando
   el access token con el refresh token cuando haga falta) desde la API o el
   worker, sin volver a pedir login mientras el refresh token siga siendo
   válido.

Es idempotente: volver a ejecutarlo sobrescribe `msgraph.env` y repite el
login (útil para rotar sesión o cambiar de cuenta).

## Dónde vive la caché de tokens y sus permisos

Variable de entorno `MSGRAPH_TOKEN_CACHE_PATH` (ver `packages/core/settings.py`
y `.env.example`), por defecto:

```
~/.openclaw/secrets/msgraph_token_cache.json
```

Igual que el resto de `~/.openclaw/secrets/`: **nunca dentro del repositorio
git, nunca en logs**, directorio con permisos `700` y fichero con `600`.
Contiene el refresh token de MSAL — quien tenga ese fichero puede obtener
access tokens de Graph para esta cuenta sin volver a autenticarse, así que
trátalo con el mismo cuidado que un token de bot de Telegram o un
`client_secret.json` de Google.

## Rotar o revocar el acceso

1. Revoca el consentimiento de la app en Azure: **Entra ID → Enterprise
   applications** → busca la app → **Permissions** → "Remove access" (o,
   desde la cuenta del propio usuario en
   [myaccount.microsoft.com](https://myaccount.microsoft.com) → "Apps y
   servicios" → revocar).
2. Borra la caché local: `rm ~/.openclaw/secrets/msgraph_token_cache.json`.
3. Repite `scripts/configure-msgraph` para volver a autenticarte desde cero.

## Pendiente (fuera de esta rama)

* Herramientas MCP de correo (`docs/EMAIL.md`, `feature/mcp-email`): leer
  bandeja, redactar borrador, enviar tras confirmación explícita (Fase 3 del
  roadmap, reutilizando `packages/security/confirmation.py` como en el
  patrón de `gog` descrito en `docs/OPENCLAW.md`).
* Herramientas MCP de calendario (`docs/CALENDAR.md`, `feature/mcp-calendar`):
  consultar disponibilidad, proponer/crear eventos tras confirmación
  (Fase 4 del roadmap).
