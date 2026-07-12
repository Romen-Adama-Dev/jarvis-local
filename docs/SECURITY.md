# Seguridad — Jarvis Local

## Estado de hardening del host

| Medida | Estado | Notas |
|---|---|---|
| Usuario de servicio dedicado | ✅ `jarvis-svc` (system, sin shell, sin sudo) | Propietario de `/srv/jarvis`. Ver `scripts/bootstrap-server`. |
| `/srv/jarvis` con permisos mínimos | ✅ `750`, propietario `jarvis-svc` | El usuario humano `jarvis` está en el grupo `jarvis-svc` para desplegar/leer logs. |
| UFW | ✅ activo, `deny incoming` por defecto, solo `22/tcp` permitido | El resto de servicios (Postgres, Redis, Qdrant, Ollama, AirLLM, OpenClaw) se vinculan a `127.0.0.1` o red interna Docker, nunca se abren en UFW. |
| SSH por clave | ⏳ Pendiente de confirmación del usuario | Se detectó `PasswordAuthentication yes` efectivo (por `/etc/ssh/sshd_config.d/99-password.conf`, que sobreescribe el `no` de cloud-init por orden de carga). Hay 2 claves en `authorized_keys`. Se desactivará `PasswordAuthentication` en cuanto el usuario confirme que el acceso por clave funciona desde su cliente. |
| sudo NOPASSWD temporal | ⚠️ Activo para `jarvis` vía `/etc/sudoers.d/jarvis-temp` | Necesario porque la ejecución de Claude Code no dispone de TTY para introducir contraseña interactiva. **Revocar al finalizar el despliegue** con `sudo rm /etc/sudoers.d/jarvis-temp`. Ver punto pendiente en `docs/OPERATIONS.md`. |
| Secretos fuera de git | ✅ `.env` en `.gitignore`, solo se versiona `.env.example` sin valores reales | |
| Exposición de servicios internos | ✅ por diseño (ver `docs/ARCHITECTURE.md`) | Se verificará con `ss -tlnp` tras levantar cada servicio en fases siguientes. |

## Principios de entrada no confiable

* Cada documento subido al RAG se trata como entrada no confiable: se delimita el contexto recuperado, no se ejecutan instrucciones contenidas en documentos, y un documento no puede alterar reglas del sistema (ver `docs/RAG.md`, sección de protección contra prompt injection, y los tests en `tests/` correspondientes a la Fase 10).
* Cada mensaje de Telegram se trata como entrada no confiable: solo el/los Telegram ID en la allowlist pueden interactuar (ver `docs/TELEGRAM.md`), y las órdenes administrativas requieren confirmación explícita con caducidad (ver `docs/OPERATIONS.md`).
* No se permite ejecución de shell arbitrario desde Telegram/OpenClaw: solo una allowlist explícita de herramientas (ver `integrations/openclaw/skills/jarvis-rag`).

## Pendientes de esta fase

* [ ] Confirmar acceso SSH por clave y desactivar `PasswordAuthentication`.
* [ ] Revocar `/etc/sudoers.d/jarvis-temp` al finalizar el despliegue inicial (Fase 15).
* [ ] Rotación del token de Telegram documentada en `docs/TELEGRAM.md` (Fase 9).
