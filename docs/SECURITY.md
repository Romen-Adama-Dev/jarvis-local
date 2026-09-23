# Seguridad — Jarvis Local

## Estado de hardening del host (VM de GCP, 23-09-2026)

Comprobado en la VM del despliegue actual (`docker compose`, NVIDIA L4). El criterio 3
de `docs/ACCEPTANCE.md` verifica la exposición real con `ss -tlnp`.

| Medida | Estado | Notas |
|---|---|---|
| Nada escucha fuera de loopback salvo SSH y Tailscale | ✅ | `ss -tlnp`: solo `sshd` (22) y `tailscaled`. Todos los servicios de Jarvis, incluidos los de monitorización, escuchan en `127.0.0.1`; OpenClaw, OpenProject y CouchDB se publican solo en el tailnet con `tailscale serve` (`docs/ACCESO-REMOTO.md`). |
| Cortafuegos | ✅ firewall de GCP | UFW está **inactivo** en la VM: el filtrado de entrada lo hace el firewall del proyecto de GCP, que solo permite SSH. En un servidor sin ese firewall, actívalo (`ufw default deny incoming`, `ufw allow 22/tcp`). |
| SSH sin contraseña | ✅ | `sshd -T`: `passwordauthentication no`, `permitrootlogin without-password`. Acceso solo con clave. |
| sudo sin contraseña | ✅ no hay reglas propias | `/etc/sudoers.d/` solo contiene lo que pone cloud-init y Google (`90-cloud-init-users`, `google_sudoers`). La regla temporal `jarvis-temp` del servidor original no existe aquí. |
| Contenedores sin privilegios | ✅ | Ningún servicio usa `privileged`. `openclaw` y `tailscale` usan `network_mode: host` por necesidad (el gateway publica por Tailscale y el agente resuelve nombres del tailnet); el resto va en la red interna de compose. |
| El agente solo ve su workspace | ✅ desde el 22-09 | `tools.fs.workspaceOnly: true` y `web_fetch` y `web_search` denegados en OpenClaw (internet solo con `jarvis_web_sources`/`jarvis_web_read` y aprobación del usuario); el gateway arranca sin los secretos que no necesita en su entorno (ver «Auditoría de seguridad» abajo). |
| Secretos fuera de git | ✅ | `.env`, `vault_ssh_key` y los datos de estado están en `.gitignore` y `.dockerignore`; solo se versiona `.env.example` sin valores reales. |
| Copias de seguridad cifradas en reposo | ⏳ | Copias diarias de Postgres, Qdrant, estado de OpenClaw y CouchDB con restauración probada (`docs/BACKUP.md`); quedan dentro de la VM, sin cifrado adicional ni copia fuera del servidor. |

> El servidor original del proyecto (bare metal con GTX 1070, julio de 2026) usaba un
> usuario de servicio `jarvis-svc` dueño de `/srv/jarvis` en modo `750`, UFW activo y
> una regla `sudo` temporal para el despliegue. Ese modelo se describe en
> `docs/OPENCLAW-HISTORICO.md` y en `scripts/bootstrap-server`, que sigue siendo válido
> para instalar sin Docker; en la VM actual los contenedores corren con el UID del
> usuario del despliegue (`JARVIS_UID`) y no hay usuario de sistema aparte.

## Principios de entrada no confiable

* Cada documento subido al RAG se trata como entrada no confiable: se delimita el contexto recuperado, no se ejecutan instrucciones contenidas en documentos, y un documento no puede alterar reglas del sistema (regla de datos no confiables en `integrations/openclaw/workspace/AGENTS.md`). Lo mismo vale para los resultados de búsqueda web, el contenido del vault y la memoria.
* Cada mensaje de Telegram se trata como entrada no confiable: solo el/los Telegram ID en la allowlist pueden interactuar (ver `docs/TELEGRAM.md`), y las órdenes administrativas requieren confirmación explícita con caducidad (`packages/security/confirmation.py`, `CONFIRMATION_TTL_SECONDS`; ver `docs/EMAIL.md`).
* La ejecución de comandos desde Telegram/OpenClaw pasa por **exec approvals** (decisión del propietario, 2026-07-13, que sustituye a la prohibición total inicial): allowlist de comandos de solo lectura que corren directos; cualquier otro comando requiere aprobación explícita del propietario con botones nativos en Telegram, y se deniega si no hay interfaz disponible (`askFallback: deny`). Los comandos corren como usuario sin privilegios, nunca root. Detalle y análisis de riesgo en `docs/OPENCLAW.md`.

## Auditoría de seguridad (22-09-2026)

Revisión completa del repositorio y del despliegue con una auditoría asistida por
agentes: 21 hallazgos, 8 confirmados con prueba reproducible. Lo corregido, en la rama
`fix/seguridad-auditoria` (PR #13):

| Severidad | Hallazgo | Corrección |
|---|---|---|
| Alta | El agente podía leer ficheros fuera de su workspace y sacar el contenido con `web_fetch` | `tools.fs.workspaceOnly` y `web_fetch` denegado |
| Alta | El gateway arrancaba con secretos que no usa (correo, CalDAV, CouchDB, Postgres, Telegram) en su entorno | `unset` antes de `exec openclaw gateway` |
| Media | El LaTeX de un documento de terceros podía incluir ficheros del contenedor en el PDF generado | pandoc sin `raw_tex`/`raw_attribute`, `openin_any=p`, `shell_escape=f` y tiempo máximo |
| Media | `vault_ssh_key` y los datos de estado no estaban ignorados | Añadidos a `.gitignore` y `.dockerignore` |
| Baja | Dos confirmaciones simultáneas consumían el mismo token y enviaban el correo dos veces | El token se consume con `GETDEL` |
| Baja | Un nombre de empresa sin caracteres latinos daba un identificador vacío y su documentación acababa como general | Se rechaza al crear; los ya guardados reciben un identificador por hash |

El informe completo (hallazgos, pruebas y descartes) **no se versiona**: queda en el
servidor, fuera del repositorio público.

## Pendiente

* [ ] Aprobación de los correos salientes por una persona fuera del modelo: hoy el propio agente puede confirmar el borrador que él mismo ha redactado.
* [ ] Roles y `allowTailscale` en el panel de OpenClaw publicado por Tailscale; activarlo ahora deja el panel inaccesible sin el token.
* [ ] Rotar el token de Telegram y la contraseña de aplicación de Gmail: quedaron expuestos en un commit del repositorio público (accesible por SHA aunque no esté en ninguna rama).
* [ ] Comprobar desde otro dispositivo del tailnet si Redis, Qdrant y Ollama son alcanzables por los servicios que usan `network_mode: host`.
