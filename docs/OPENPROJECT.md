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
* **`jarvis-pm`** (`integrations/openclaw/skills/jarvis-pm`) tiene seis herramientas a
  propósito: listar y crear proyectos, listar, crear y actualizar trabajo, e informe de
  seguimiento. Los servidores MCP de la comunidad exponen más de cien herramientas y un
  modelo local se pierde entre ellas. La lógica vive en `packages/openproject`.
* **Tipos**: Tarea, Hito y **Riesgo** (lo crea el aprovisionamiento, con los mismos
  estados que Tarea). En OpenProject puedes activar más tipos por proyecto (Épico,
  Historia de usuario, Error...).
* Jarvis actúa como el usuario **Jarvis (asistente)**, así que en el historial de cada
  tarea se ve qué hizo él y qué hiciste tú. No manda correos ni borra nada.

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
| `openproject-setup` | Migraciones y datos iniciales en español; tipo Riesgo; usuario `jarvis` con su clave de API; borra los proyectos de demostración la primera vez; el admin entra como miembro de todos los proyectos |
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

Para asignar trabajo a alguien, esa persona tiene que ser miembro del proyecto (en la web:
proyecto → Miembros). El admin se añade solo a cada proyecto que crea Jarvis.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Jarvis dice "OpenProject no está configurado" | Falta el perfil `pm` o el servicio `init` no generó `openproject_api_key`: `docker compose up -d`. |
| "OpenProject rechazó la clave de API" | Se borró el volumen o la base: `docker compose up -d openproject-setup` vuelve a registrar la clave. |
| `openproject-setup` falla | `docker compose logs openproject-setup`. Se puede relanzar sin riesgo: todo lo que hace es idempotente. |
| La web responde "Invalid host_name configuration" | Entraste por un nombre que no es el de Tailscale ni `127.0.0.1:8090`. Si cambiaste `TAILSCALE_HOSTNAME`, reinicia `openproject` y `openproject-worker`. |
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
