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

## Los siete casos de criterio — resueltos el 23-09

| # | Qué pasaba | Qué se ha hecho |
|---|---|---|
| A | `docs/OPENCLAW.md` mezclaba la instalación con systemd (julio) y la de Docker (septiembre), con secciones largas de incidentes con Qwen que ya no aplican a Gemma | Dividido: `docs/OPENCLAW.md` describe solo el despliegue con Docker y conserva un resumen «Lecciones que siguen vigentes»; la instalación sin Docker, los incidentes de julio (prompt gigante, latencia), el watchdog de systemd y las notas del despliegue de septiembre pasan a `docs/OPENCLAW-HISTORICO.md` |
| B | La sección «Correo y calendario (gog)» describía OAuth de Google, sustituido por IMAP/SMTP y CalDAV/OpenProject | La sección vigente remite a `docs/EMAIL.md` y `docs/CALENDAR.md`; `gog` queda en el documento histórico, con las referencias de `MSGRAPH.md` y `ROADMAP.md` actualizadas |
| C | `docs/ARCHITECTURE.md` describía el hardware del servidor original y el diagrama no incluía OpenProject, LiveSync ni Tailscale | Reescrito: despliegue actual (VM de GCP con L4, compose y perfiles), diagrama con OpenProject, vault, LiveSync/CouchDB, Tailscale, SearXNG y monitorización, lista de paquetes al día y el servidor original reducido a una nota |
| D | La tabla de hardening de `docs/SECURITY.md` y sus pendientes eran del servidor original | Comprobado en la VM (`ss -tlnp`, `sshd -T`, `/etc/sudoers.d`, UFW) y rehecha con lo que es cierto hoy; añadido el resumen de la auditoría del 22-09 y los pendientes reales |
| E | La sección de exec de `AGENTS.md` citaba `nvidia-smi` y `ollama` y decía que `write`/`edit` llegan al home | Ya corregido en `fix/seguridad-auditoria` (PR #13), que además limita las herramientas de ficheros al workspace |
| F | Los niveles `vram_7000` y `vram_21000` de `BENCHMARKS.md`/`MODELS.md` no están medidos | Nada que corregir: los propios documentos lo dicen. Revisar solo si se cambia de GPU |
| G | `docs/TEAMS.md` describía un canal preparado pero sin probar | El documento abre con un aviso de estado: preparado, sin probar y fuera del alcance verificado del TFM. **La decisión de si Teams sigue en el alcance sigue siendo tuya**; si se descarta, el documento y `scripts/configure-teams` se pueden retirar en un commit aparte |

## Pendiente de tu criterio

* **G**: decidir si Microsoft Teams sigue en el alcance del TFM.
