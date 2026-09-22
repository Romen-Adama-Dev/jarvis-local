# Coherencia de la documentación — informe (22-09-2026)

Revisión de todos los `.md` del repo (salvo las skills de terceros, que se revisaron al
copiarlas) contra el código, `compose.yml`, `.env.example`, la plantilla de OpenClaw y
entre sí. Comprobaciones automáticas: enlaces relativos, rutas citadas entre comillas
invertidas, variables de entorno citadas, perfiles de compose y modelos por nivel de
VRAM. Después, lectura de los documentos con más afirmaciones de estado (README,
OPENCLAW, SECURITY, ARCHITECTURE, ACCEPTANCE, INSTALL, DOCKER, TELEGRAM, MODELS).

Resultado de las comprobaciones automáticas: ningún enlace roto; rutas inexistentes solo
`docs/OPERATIONS.md` y `docs/RAG.md` (corregidas); `MODELS.md` coincide con
`scripts/select-models`; `AIRLLM_QUEUE_MAX_PENDING` parecía no existir pero es válida
(prefijo `AIRLLM_` de pydantic-settings).

## Corregido en esta rama

| # | Dónde | Incoherencia | Corrección |
|---|---|---|---|
| 1 | `README.md` «Estado» | «en curso la Fase 6» frente a `ROADMAP.md` 4.1, que la da por cerrada el 21-09 | Fases 0 a 6 hechas |
| 2 | `docs/TELEGRAM.md` | «`/upload` aún no conectado» frente a `OPENCLAW.md` y `AGENTS.md`, donde la subida desde Telegram funciona (criterios 11-12) | Describe el flujo actual con `jarvis_upload` |
| 3 | `docs/OPENCLAW.md` «Configuración» | Modelo `qwen2.5:7b` (hoy `OLLAMA_PRIMARY_MODEL`, `gemma4` en la L4) | Remite a `MODELS.md` |
| 4 | `docs/OPENCLAW.md` «Configuración» | `memorySearch.enabled: false`, cuando la plantilla activa `memory.search` con `embeddinggemma` local | Describe la configuración real |
| 5 | `docs/OPENCLAW.md` «Configuración» | `tools.deny` incluye `exec` y «el agente no tiene ninguna vía de shell», que contradice la sección de exec approvals del mismo documento | Aclara que `exec` va por aprobación desde el 13-07 |
| 6 | `docs/OPENCLAW.md` skill `jarvis-rag` | «Pendiente: subida de documentos», que contradice la sección «Subida de documentos al RAG desde Telegram» | Queda solo la reindexación como pendiente |
| 7 | `docs/OPENCLAW.md` skill `jarvis-rag` | Se lanza con `uv run --frozen --project /home/jarvis/...`; hoy con `<repo>/.venv/bin/python` | Corregido; la tabla de herramientas remite a `AGENTS.md`/`SKILL.md` para la lista vigente |
| 8 | `docs/OPENCLAW.md` exec approvals | La lista blanca incluye `nvidia-smi` y `ollama`, que `docker-entrypoint.sh` no añade | Separa Docker y la instalación sin Docker |
| 9 | `docs/OPENCLAW.md` SearXNG | «perfil `assistant`», pero `searxng` es un servicio por defecto (OpenClaw depende de él) | Corregido, también el comando |
| 10 | `docs/OPENCLAW.md` | Mezcla sin avisar la instalación con Docker y la de systemd | Nota al principio que dice qué secciones son de la instalación sin Docker |
| 11 | `docs/SECURITY.md` | Remite a `docs/OPERATIONS.md` y `docs/RAG.md`, que no existen | Remite a documentos que existen |
| 12 | `docs/SECURITY.md` | «aún no existe `Dockerfile`», pero existe | Pendiente marcado como hecho, con lo que falta (servicios en `network_mode: host`) |
| 13 | `docs/SECURITY.md` frente a `ACCEPTANCE.md` (criterio 3) | «UFW activo» frente a «UFW inactivo en la VM» | Nota: la tabla es la del servidor original |
| 14 | `docs/ARCHITECTURE.md` | Hardware GTX 1070 como si fuera el actual; remite a `OPERATIONS.md` | Nota con el despliegue actual; referencia quitada |
| 15 | `docs/INSTALL.md` | «El despliegue real corre con systemd, no en Docker» | Desde el 15-09 el real es Docker Compose |
| 16 | `docs/DOCKER.md` | Falta el perfil `deep` en la tabla de perfiles | Añadido |
| 17 | `docs/ACCEPTANCE.md` | Criterio 5 en ✅ sin decir que AirLLM está desactivado (criterio 16); criterio 23 con un número de tests fijo | Aclarado |

## Pendiente de tu criterio

| # | Dónde | Qué pasa | Propuesta |
|---|---|---|---|
| A | `docs/OPENCLAW.md` entero | Mitad instalación con systemd (julio), mitad Docker (septiembre); secciones largas de incidentes con Qwen (prompt gigante, latencia) que ya no aplican a Gemma | Dividirlo en `OPENCLAW.md` (Docker, vigente) y `OPENCLAW-BAREMETAL.md` o un anexo histórico |
| B | `docs/OPENCLAW.md` «Correo y calendario (gog)» | Describe `gog` con OAuth de Google, sustituido por IMAP/SMTP + CalDAV/OpenProject y las skills `jarvis-email`/`jarvis-calendar` (`EMAIL.md`, `CALENDAR.md`) | Borrar la sección o moverla al anexo histórico |
| C | `docs/ARCHITECTURE.md` | Toda la sección de hardware y el usuario `jarvis-svc` son del servidor original; el diagrama no incluye OpenProject, LiveSync ni Tailscale | Reescribir con la arquitectura de compose |
| D | `docs/SECURITY.md` | La tabla de hardening y los pendientes (SSH por clave, `sudoers.d/jarvis-temp`) son del servidor original; no se sabe si aplican a la VM | Confirmar en la VM y rehacer la tabla; enlazar el resumen de la auditoría de seguridad del 22-09 |
| E | `integrations/openclaw/workspace/AGENTS.md` (sección exec) | Cita `nvidia-smi` y `ollama` en la lista blanca (en Docker no están) y dice que `write`/`edit` llegan al home | Corregido en la rama `fix/seguridad-auditoria`, que limita las herramientas de ficheros al workspace |
| F | `docs/BENCHMARKS.md`, `docs/MODELS.md` | Los niveles distintos de `vram_7000` y `vram_21000` no están medidos (lo dicen ellos mismos) | Nada que corregir; revisar si se cambia de GPU |
| G | `docs/TEAMS.md` | Canal preparado pero sin probar (falta el registro en Azure) | Decidir si Teams sigue en el alcance del TFM |
