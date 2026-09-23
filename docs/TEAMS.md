# Microsoft Teams — integración

> **Estado (23-09-2026): preparado, sin probar, fuera del alcance verificado del TFM.**
> El canal está soportado en la configuración y hay guion de configuración
> (`scripts/configure-teams`), pero falta el registro de Azure Bot y un túnel público
> hacia el *messaging endpoint*, que no se pueden montar en este despliegue. Nada de
> Teams está verificado en `docs/ACCEPTANCE.md`. Este documento describe cómo se
> activaría, no algo que esté funcionando.

Segundo canal de conversación, además de Telegram (`docs/TELEGRAM.md`). Mismo
agente OpenClaw, misma skill MCP `jarvis-rag`: OpenClaw es agnóstico de canal,
así que Teams no necesita ninguna herramienta nueva ni una "capa MCP" aparte —
solo activar el canal. La Fase 1 del roadmap (`docs/ROADMAP.md`) ya está
cubierta por `jarvis-rag` desde la Fase 9; esto es la Fase 5 (segundo canal).

## Diferencia clave con Telegram: requiere entrada, no solo salida

Telegram funciona por *long polling*: OpenClaw abre la conexión hacia
Telegram, nunca al revés, así que no expone nada. **Teams funciona al
contrario**: el conector Bot Framework de Microsoft necesita poder llamar a
un *messaging endpoint* HTTPS tuyo (`webhook.port`/`webhook.path`, por
defecto `3978`/`/api/messages`) cada vez que alguien te escribe. Eso exige
que ese puerto sea alcanzable desde internet, lo cual choca de entrada con
`docs/SECURITY.md` (UFW deniega todo salvo `22/tcp`, todo servicio en
`127.0.0.1` o red interna Docker).

**No abras el puerto en UFW.** Usa un túnel saliente (p. ej. Cloudflare
Tunnel) desde `127.0.0.1:3978` hacia un hostname público: el gateway sigue
escuchando solo en loopback, UFW no cambia, y el túnel es la única superficie
nueva (revocable, con TLS gestionado por el proveedor del túnel). Documentar
la puesta en marcha exacta del túnel queda pendiente de una fase futura; este
documento asume que existe un hostname HTTPS público apuntando al puerto del
webhook antes de registrar el bot en Azure (Azure exige la URL del endpoint
en el registro).

## Registro del bot en Azure (paso único del propietario)

Solo tú puedes hacerlo, con acceso al tenant de Microsoft 365/Azure AD que
vayas a usar — igual que el alta en `@BotFather` para Telegram:

1. Azure Portal → **Azure Bot** → crear recurso. Anota el **App ID**.
2. En el registro de la app (Entra ID): **Certificates & secrets** → nuevo
   **client secret**. Anota el valor (solo se muestra una vez).
3. Anota el **Tenant ID** (Entra ID → Overview).
4. En el recurso Azure Bot: **Configuration** → **Messaging endpoint** =
   `https://<tu-hostname-del-túnel>/api/messages`.
5. **Channels** → añadir el canal **Microsoft Teams**.
6. Construir y subir el manifiesto de la app de Teams (paquete `.zip` con
   `manifest.json` + iconos) en el **Teams admin center** o compartirlo
   directamente con los usuarios autorizados. La plantilla del manifiesto no
   está versionada aquí todavía (pendiente).

## Plugin e instalación

`@openclaw/msteams` se separó del núcleo de OpenClaw (desde 2026.1.15) y se
instala como plugin aparte:

```bash
openclaw plugins install @openclaw/msteams
```

`scripts/configure-teams` lo instala si falta, guarda las credenciales fuera
del repo y activa el canal en `openclaw.json`.

## Configuración (`channels.msteams`)

| Clave | Variable de entorno | Notas |
|---|---|---|
| `enabled` | — | `false` en la plantilla; `scripts/configure-teams` lo activa. |
| `authType` | `MSTEAMS_AUTH_TYPE` | `"secret"` (client secret) o `"federated"` (certificado/managed identity). Usamos `"secret"`, más simple para un solo tenant. |
| `appId` | `MSTEAMS_APP_ID` | Del registro Azure Bot. |
| `appPassword` | `MSTEAMS_APP_PASSWORD` | El client secret. **Nunca en `openclaw.json` ni en git**: solo como variable de entorno del proceso del gateway (ver más abajo). |
| `tenantId` | `MSTEAMS_TENANT_ID` | Del Entra ID del tenant. |
| `dmPolicy` | — | `"allowlist"`, igual criterio que Telegram. |
| `allowFrom` | — | Lista de **AAD object ID** (no hay username/número aquí) autorizados a hablar con el bot. |
| `webhook.port` / `webhook.path` | — | `3978` / `/api/messages` por defecto; deben coincidir con el *messaging endpoint* configurado en Azure. |

Las credenciales (`appId`, `appPassword`, `tenantId`) se guardan en
`~/.openclaw/secrets/msteams.env` (permisos `600`) y se inyectan al proceso
del gateway mediante un *drop-in* de systemd (`EnvironmentFile=`), nunca como
valores literales en `openclaw.json` — mismo principio que el `tokenFile` de
Telegram, adaptado a cómo esta integración espera los secretos.

## Seguridad

* Mismo patrón que Telegram: `dmPolicy: "allowlist"` con la lista de AAD
  object IDs autorizados; cualquier otro remitente queda fuera antes de
  llegar al agente.
* Aprobaciones y encuestas se entregan como **Adaptive Cards** nativas de
  Teams — el mismo flujo de aprobación explícita ya usado en Telegram
  (`docs/OPENCLAW.md`, exec approvals) funciona igual aquí, sin cambios en
  `tools.exec` ni en la skill `jarvis-rag`.
* El client secret expira (según lo configurado en Azure): rotarlo repitiendo
  el paso 2 y volviendo a ejecutar `scripts/configure-teams` con el nuevo
  valor.

## Pendiente

* Plantilla del manifiesto de la app de Teams (`manifest.json` + iconos) sin
  versionar todavía.
* Puesta en marcha documentada del túnel (Cloudflare Tunnel u otro) hacia
  `127.0.0.1:3978`.
* Verificación end-to-end (mensaje real ida y vuelta) pendiente de que el
  propietario complete el registro en Azure.
