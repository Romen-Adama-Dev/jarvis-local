# Administración desde Telegram (`jarvis-admin`)

Jarvis puede administrar parte del servidor desde el chat, siempre con tu aprobación:

| Orden | Qué hace |
|---|---|
| `jarvis-admin servicios` | Estado de los contenedores |
| `jarvis-admin registros SERVICIO [LÍNEAS]` | Últimas líneas del registro (máx. 200), sin secretos |
| `jarvis-admin reiniciar SERVICIO` | Reinicia un servicio (nunca `admin` ni `init`) |
| `jarvis-admin repo preparar jarvis/feat-algo` | Copia limpia de `main` en una rama nueva, en `repo/` del workspace de Jarvis |
| `jarvis-admin repo estado` | Rama y archivos cambiados en esa copia |
| `jarvis-admin repo pr "Título" "Descripción"` | Commit, push y pull request contra `main` |
| `jarvis-admin op usuarios` | Usuarios de OpenProject |
| `jarvis-admin op usuario-nuevo "Nombre Apellido" correo@ejemplo.com` | Alta como invitado: OpenProject le manda el enlace para entrar |
| `jarvis-admin op miembro PROYECTO USUARIO [ROL]` | Añade a alguien a un proyecto |

## Cómo se aprueba

`jarvis-admin` no está en la lista blanca de `exec`, así que cada llamada te pide aprobación
en Telegram con el comando completo a la vista. Si no la das, no se ejecuta.

Los cambios al código nunca se aplican directamente: Jarvis abre una pull request y tú la
revisas y la fusionas. Se aplican al redesplegar (`docker compose up -d --build`).

## Piezas

- **Servicio `admin`** (perfil `admin`, `infra/docker/admin/`): es el único contenedor con
  el socket de Docker. Escucha solo en `127.0.0.1:8096` y exige el token que genera `init`
  (`/run/jarvis/jarvis_admin_token`). Monta el repo en solo lectura para usar `compose.yml`.
- **`jarvis-admin`** (imagen de OpenClaw): cliente de ese servicio. Las órdenes de OpenProject
  van directas a su API con la clave del usuario administrador `jarvis` (perfil `pm`).
- El contenedor de OpenClaw **no** tiene el socket de Docker ni el token de GitHub:
  `docker-entrypoint.sh` quita del entorno `JARVIS_ADMIN_GITHUB_TOKEN` y `JARVIS_ADMIN_TOKEN`
  antes de arrancar el gateway.

## Qué comprueba el servicio por su cuenta

Estas comprobaciones valen aunque se apruebe una orden por error:

- Ramas solo con la forma `jarvis/{feat,fix,docs,chore,refactor}-…`: nunca toca `main` ni las
  ramas de otros, y el push no fuerza (si la rama ya existe en GitHub, falla).
- No sube `.env*` (salvo `.env.example`), claves (`*.pem`, `*.key`, `id_*`) ni `backups/`.
- Cancela la PR si el diff añade un secreto: los valores de `.env` con nombre de secreto, los
  de `/run/jarvis` y los que tienen forma de token (GitHub, Telegram, claves privadas…).
- Quita esos mismos secretos de los registros y de los errores que devuelve.

## Activarlo

1. Crea un token de GitHub de grano fino solo para este repositorio, con permisos
   **Contents** y **Pull requests** de lectura y escritura.
2. En `.env`:

   ```bash
   COMPOSE_PROFILES=...,admin
   JARVIS_ADMIN_REPO=usuario/jarvis-local
   JARVIS_ADMIN_GITHUB_TOKEN=github_pat_...
   ```

3. `docker compose up -d --build admin openclaw` (openclaw, para que tenga `jarvis-admin`).
4. Prueba desde Telegram: «¿cómo están los servicios?» → aprueba `jarvis-admin servicios`.

Sin el perfil `admin`, `jarvis-admin` responde que el servicio no está activo. Las órdenes
`op` funcionan igual con el perfil `pm`.

## Riesgo que asumes

Montar el socket de Docker equivale a dar root en el servidor a ese contenedor. Por eso
`admin` solo expone las acciones de la tabla, solo escucha en loopback y pide token. Si no lo
necesitas, deja el perfil `admin` desactivado.
