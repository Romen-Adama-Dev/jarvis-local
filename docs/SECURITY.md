# Seguridad — Jarvis Local

## Estado de hardening del host

Esta tabla es la del servidor original (bare metal, julio de 2026). En la VM de GCP actual UFW está inactivo y filtra el firewall de GCP; la exposición real está verificada en el criterio 3 de `docs/ACCEPTANCE.md`.

| Medida | Estado | Notas |
|---|---|---|
| Usuario de servicio dedicado | ✅ `jarvis-svc` (system, sin shell, sin sudo) | Propietario de `/srv/jarvis`. Ver `scripts/bootstrap-server`. |
| `/srv/jarvis` con permisos mínimos | ✅ `750`, propietario `jarvis-svc` | El usuario humano `jarvis` está en el grupo `jarvis-svc` para desplegar/leer logs. |
| UFW | ✅ activo, `deny incoming` por defecto, solo `22/tcp` permitido | El resto de servicios (Postgres, Redis, Qdrant, Ollama, OpenClaw) se vinculan a `127.0.0.1` o red interna Docker, nunca se abren en UFW. |
| SSH por clave | ⏳ Pendiente de confirmación del usuario | Se detectó `PasswordAuthentication yes` efectivo (por `/etc/ssh/sshd_config.d/99-password.conf`, que sobreescribe el `no` de cloud-init por orden de carga). Hay 2 claves en `authorized_keys`. Se desactivará `PasswordAuthentication` en cuanto el usuario confirme que el acceso por clave funciona desde su cliente. |
| sudo NOPASSWD temporal | ⚠️ Activo para `jarvis` vía `/etc/sudoers.d/jarvis-temp` | Necesario porque la ejecución de Claude Code no dispone de TTY para introducir contraseña interactiva. **Revocar al finalizar el despliegue** con `sudo rm /etc/sudoers.d/jarvis-temp`. Ver «Pendientes de esta fase» abajo. |
| Secretos fuera de git | ✅ `.env` en `.gitignore`, solo se versiona `.env.example` sin valores reales | |
| Exposición de servicios internos | ✅ por diseño (ver `docs/ARCHITECTURE.md`) | Se verificará con `ss -tlnp` tras levantar cada servicio en fases siguientes. |

## Principios de entrada no confiable

* Cada documento subido al RAG se trata como entrada no confiable: se delimita el contexto recuperado, no se ejecutan instrucciones contenidas en documentos, y un documento no puede alterar reglas del sistema (regla de datos no confiables en `integrations/openclaw/workspace/AGENTS.md`).
* Cada mensaje de Telegram se trata como entrada no confiable: solo el/los Telegram ID en la allowlist pueden interactuar (ver `docs/TELEGRAM.md`), y las órdenes administrativas requieren confirmación explícita con caducidad (`packages/security/confirmation.py`, `CONFIRMATION_TTL_SECONDS`; ver `docs/EMAIL.md`).
* La ejecución de comandos desde Telegram/OpenClaw pasa por **exec approvals** (decisión del propietario, 2026-07-13, que sustituye a la prohibición total inicial): allowlist de comandos de solo lectura que corren directos; cualquier otro comando requiere aprobación explícita del propietario con botones nativos en Telegram, y se deniega si no hay interfaz disponible (`askFallback: deny`). Los comandos corren como usuario `jarvis`, nunca root. Detalle y análisis de riesgo en `docs/OPENCLAW.md`.

## Pendientes de esta fase

* [ ] Confirmar acceso SSH por clave y desactivar `PasswordAuthentication`.
* [ ] Revocar `/etc/sudoers.d/jarvis-temp` al finalizar el despliegue inicial (Fase 15).
* [ ] Rotación del token de Telegram documentada en `docs/TELEGRAM.md` (Fase 9).
* [x] Imagen Docker propia (`Dockerfile`, `compose.yml`): servicios publicados solo en `127.0.0.1` (criterio 3 de `docs/ACCEPTANCE.md`). Queda revisar los que usan `network_mode: host` (openclaw, tailscale).
