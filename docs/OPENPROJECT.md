# OpenProject: gestión de proyectos desde Telegram

OpenProject es la alternativa libre a Jira + Confluence: tableros, paquetes de trabajo
(tareas, hitos, riesgos), Gantt, wiki y reuniones. Jarvis lo maneja desde Telegram con la
skill `jarvis-pm` y tú lo ves y editas en el navegador por Tailscale. Todo corre en el
servidor: ningún dato de proyecto sale de él.

## Cómo funciona

```
Telegram ──► OpenClaw (Gemma) ──► MCP jarvis-pm ──► API v3 ──┐
                                                               ▼
navegador (PC, móvil) ──Tailscale──► https://jarvis.<tailnet>.ts.net:8445 ──► openproject
                                                                              │
                                                     postgres (base "openproject")
```

* **Organización multiempresa**: cada **empresa** es un proyecto raíz y sus **proyectos**
  cuelgan de ella. Los permisos, tableros y el Gantt de OpenProject respetan esa
  jerarquía.
* **`jarvis-pm`** (`integrations/openclaw/skills/jarvis-pm`) tiene pocas herramientas a
  propósito: listar y crear proyectos; listar, crear y actualizar trabajo; informe de
  seguimiento; reuniones; importar actas; y convertir un correo en tarea. Los servidores MCP de la comunidad exponen más de cien herramientas y un
  modelo local se pierde entre ellas. La lógica vive en `packages/openproject`.
* **Tipos**: Tarea, Hito y **Riesgo** (lo crea el aprovisionamiento, con los mismos
  estados que Tarea). En OpenProject puedes activar más tipos por proyecto (Épico,
  Historia de usuario, Error...).
* Jarvis actúa como el usuario **Jarvis (asistente)**, así que en el historial de cada
  tarea se ve qué hizo él y qué hiciste tú. No borra nada; los únicos correos son las
  invitaciones a reuniones que confirmes.
* **Wiki**: la página *Memoria de Jarvis* de cada proyecto es su nota del vault de
  Obsidian (se edita allí) y el resto de páginas de la wiki se copian al vault
  (`docs/OBSIDIAN.md`, "Una sola memoria").
* **Reuniones y calendario**: con `CALENDAR_PROVIDER=openproject` el calendario de Jarvis
  son las reuniones de OpenProject (`docs/CALENDAR.md`).
* **Correo**: OpenProject envía avisos e invitaciones por la cuenta SMTP de Jarvis
  (`MAIL_*`, `docs/EMAIL.md`) y el admin tiene ese mismo correo (o
  `OPENPROJECT_ADMIN_MAIL`). El usuario Jarvis no recibe avisos.

## Activarlo

1. En `.env`, añade `pm` a los perfiles (con `tailscale` para verlo desde fuera):

   ```bash
   COMPOSE_PROFILES=vault,tailscale,livesync,pm
   ```

2. Arranca: `docker compose up -d --build`. La primera vez `openproject-setup` crea la
   base de datos y tarda unos minutos; `docker compose logs -f openproject-setup` termina
   con `OpenProject listo para Jarvis`.
3. Entra en `https://jarvis.<tailnet>.ts.net:8445` (o `http://127.0.0.1:8090` por túnel
   SSH) con el usuario `admin` y la contraseña de:

   ```bash
   docker compose exec openclaw cat /run/jarvis/openproject_admin_password
   ```

Qué hace el arranque en cada `up`:

| Servicio | Qué hace |
|---|---|
| `init` | Genera secretos: clave de sesión, contraseña de la base, del admin y clave de API de Jarvis |
| `openproject-db-init` | Crea el rol y la base `openproject` en el PostgreSQL de Jarvis |
| `openproject-setup` | Migraciones y datos iniciales en español; tipo Riesgo; usuario `jarvis` con su clave de API y sin avisos; borra los proyectos de demostración la primera vez; el admin entra como miembro de todos los proyectos y recibe el correo de Jarvis |
| `openproject`, `openproject-worker` | Web (puerto 8090 en `127.0.0.1`) y trabajos en segundo plano |
| `openproject-cache` | memcached |
| `tailscale` | Publica el puerto 8445 del tailnet hacia `127.0.0.1:8090` |

## Usarlo desde Telegram

| Dices | Jarvis usa |
|---|---|
| "Da de alta la empresa Acme" | `pm_create_project(name="Acme")` |
| "Crea el proyecto Migración ERP de Acme" | `pm_create_project(name="Migración ERP", company="Acme")` |
| "Apunta en Migración ERP la tarea X para el viernes, asignada a Ana" | `pm_create_task` |
| "Registra el riesgo Y: probabilidad alta, impacto medio..." | `pm_create_task(kind="Riesgo")` |
| "¿Qué vence esta semana en Migración ERP?" / "¿qué va con retraso?" | `pm_list_tasks` |
| "Pasa la #38 a cerrada y comenta que se hizo el 15" | `pm_update_task` |
| "¿Cómo va Migración ERP?" | `pm_status_report`: abiertos por estado y tipo, vencidos, próximos 7 días, hitos, riesgos y enlaces al Gantt y a los tableros |
| "Reunión de seguimiento de Web corporativa el jueves a las 10 por Meet" | `jarvis_calendar_propose_event(project=...)` y, tras tu "sí", `jarvis_calendar_confirm_event`: reunión en el módulo Reuniones con invitación |
| "¿Qué reuniones tengo esta semana?" | `pm_meetings` o `jarvis_calendar_availability` |
| "Pasa el correo del cliente a tarea de Web corporativa" | `pm_task_from_email(project, message_id)`: asunto como título, remitente y texto en la descripción |
| "Sí, pásalo a OpenProject" (tras un acta) | `pm_import_minutes`: tareas, riesgos y la reunión cerrada con el acta |

Para asignar trabajo a alguien, esa persona tiene que ser miembro del proyecto (en la web:
proyecto → Miembros). El admin se añade solo a cada proyecto que crea Jarvis.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Jarvis dice "OpenProject no está configurado" | Falta el perfil `pm` o el servicio `init` no generó `openproject_api_key`: `docker compose up -d`. |
| "OpenProject rechazó la clave de API" | Se borró el volumen o la base: `docker compose up -d openproject-setup` vuelve a registrar la clave. |
| `openproject-setup` falla | `docker compose logs openproject-setup`. Se puede relanzar sin riesgo: todo lo que hace es idempotente. |
| La web responde "Invalid host_name configuration" | Entraste por un nombre que no es el de Tailscale ni `127.0.0.1:8090`. Si cambiaste `TAILSCALE_HOSTNAME`, reinicia `openproject` y `openproject-worker`. |
| No llegan invitaciones ni avisos | Falta la cuenta de correo (`MAIL_*`, `scripts/configure-mail`) o `MAIL_PROVIDER` no es `imap`. `docker compose up -d` recrea OpenProject con ella; `docker compose logs openproject-worker \| grep MailerJob` muestra los envíos. |
| No carga por Tailscale | `docker compose exec tailscale tailscale --socket /var/run/tailscale/tailscaled.sock serve status` debe mostrar el puerto 8445. |

## Datos y copia de seguridad

* Base de datos: `openproject` dentro del servicio `postgres` (volumen `postgres_data`).
* Adjuntos: volumen `openproject_assets`.
* Para borrarlo todo: quita `pm` de `COMPOSE_PROFILES`, `docker compose up -d
  --remove-orphans`, `docker volume rm jarvis-local_openproject_assets` y
  `docker compose exec postgres dropdb -U jarvis openproject`.

## Versiones fijadas

| Pieza | Versión |
|---|---|
| OpenProject | imagen `openproject/openproject:17.8.0-slim` |
| memcached | `memcached:1.6.39-alpine` |

## Alternativas consideradas

* **Plane**: MCP oficial, más orientado a Scrum que a gestión formal (sin presupuestos ni
  reuniones); buena opción si solo se quiere un tablero ágil.
* **Servidor MCP oficial de OpenProject**: solo en la edición Enterprise de pago.
* **MCP de la comunidad** (`jtauschl/openproject-mcp`, 116 herramientas): demasiadas
  para un modelo local.
