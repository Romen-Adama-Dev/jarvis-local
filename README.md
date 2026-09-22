# Jarvis Local

Asistente de IA privado y local para *project managers* (TFM JARVIS-PMI): RAG sobre la
documentación propia separada por empresa y proyecto, gestión de proyectos con
OpenProject, actas de reunión automáticas, correo y calendario, documentos generados y
memoria en Obsidian, todo manejado desde Telegram. La inferencia (Ollama con GPU) y el RAG
son 100 % locales: ningún documento, embedding, prompt o respuesta sale del servidor hacia
APIs de modelos en la nube. Solo salen los mensajes de Telegram y lo que Jarvis envía o lee
en tu cuenta de correo.

## Arranque rápido

```bash
cp .env.example .env   # rellena TELEGRAM_BOT_TOKEN y TELEGRAM_AUTHORIZED_USER_IDS
docker compose up -d
scripts/check-integrations   # comprueba que cada integración responde
```

Requiere Docker con Compose v2.30+ y, para GPU, NVIDIA Container Toolkit (sin GPU:
`compose.cpu.yml`). El primer arranque genera los secretos y elige el modelo según la
VRAM (`docs/MODELS.md`). Detalles en `docs/DOCKER.md`.

Perfiles opcionales en `COMPOSE_PROFILES` (`.env`):

| Perfil | Qué añade | Guía |
|---|---|---|
| `tailscale` | Panel de OpenClaw, OpenProject y Obsidian desde el móvil o el portátil, sin abrir puertos | `docs/ACCESO-REMOTO.md` |
| `pm` | OpenProject: empresas, proyectos, tareas, hitos, riesgos, Gantt, reuniones | `docs/OPENPROJECT.md` |
| `backup` | Copia de seguridad diaria y restauración probada | `docs/BACKUP.md` |
| `livesync` | Memoria de Jarvis en Obsidian del iPhone y el portátil | `docs/OBSIDIAN.md` |
| `vault` | Historial del vault de Obsidian en un repositorio git privado | `docs/MEMORY.md` |
| `monitoring` | Panel de Grafana (servicios, API, GPU, servidor) y alertas por Telegram | `docs/MONITORING.md` |

## Qué hace desde Telegram

* **Preguntas sobre tu documentación** con cita de la fuente y abstención si no hay
  evidencia; documentos separados por empresa y proyecto (`docs/EMPRESAS.md`).
* **Proyectos** en OpenProject: altas, tareas, hitos, riesgos, cambios de estado e
  informe de seguimiento (`docs/OPENPROJECT.md`).
* **Reuniones y calendario**: la agenda son las reuniones de OpenProject y los
  vencimientos; crear una reunión invita a los participantes por correo con .ics
  (`docs/CALENDAR.md`). También CalDAV o Microsoft 365.
* **Actas**: de la grabación a acta en PDF/Word, nota en Obsidian, documentación del
  proyecto y, si confirmas, tareas, riesgos y reunión en OpenProject (`docs/ACTAS.md`).
* **Correo** por IMAP/SMTP (Gmail u otro con contraseña de aplicación) o Microsoft 365:
  leer, redactar y enviar con confirmación, adjuntar documentos, pasar un correo a
  tarea (`docs/EMAIL.md`). OpenProject envía por la misma cuenta.
* **Una sola memoria** en Obsidian: red de conocimiento con empresas, proyectos,
  personas, hitos, riesgos, reuniones y documentos enlazados (vista de grafo), compartida
  con la wiki de OpenProject; "recuerda que…" por Telegram la amplía (`docs/OBSIDIAN.md`).
* **Coaching ágil** (retros, planificación de sprint, historias de usuario, métricas y
  salud del equipo) con la skill de ClawHub `agile-toolkit`, revisada y copiada en el repo
  (`integrations/openclaw/skills-terceros/README.md`).
* **Documentos generados** desde el RAG (resumen, DAFO, planes) en DOCX/PPTX/PDF, y
  **documentos ofimáticos a medida** en Excel, Word, PowerPoint y OpenDocument
  (`.xlsx/.docx/.pptx/.ods/.odt/.odp`) con tablas, negritas y totales, incluida la
  exportación de tareas de OpenProject a Excel (`docs/DOCGEN.md`), **voz** local (whisper + Piper), **búsqueda web** con SearXNG y
  **directorio de servicios** con enlaces y estado.

* **Menú de botones** con `/menu`: acta de reunión, añadir a la memoria, tarea en
  OpenProject, informe de estado, búsqueda web y agenda, sin escribir comandos; lo que
  escribe sigue pidiendo tu «sí» (`docs/TELEGRAM.md`).

Para probarlo todo con un proyecto ficticio (incluido el guion del audio de una reunión):
`docs/DEMO.md`.

Toda acción con efectos fuera del servidor (enviar un correo, invitar a una reunión,
crear tareas desde un acta) pide un "sí" explícito antes.

## Estado

Fases 0 a 5.3 hechas; en curso la Fase 6 (monitorización, copias de seguridad, CI).
Estado detallado y lo que queda en `docs/ROADMAP.md`; criterios de aceptación en
`docs/ACCEPTANCE.md`; arquitectura en `docs/ARCHITECTURE.md`.

## Estructura

```text
apps/            API (FastAPI) y worker (arq)
packages/        Dominio: core, security, documents, rag, inference, meetings, docgen,
                 office, openproject, imapsmtp, caldavcal, msgraph
services/airllm/ Microservicio AirLLM (modo /deep)
integrations/    OpenClaw: imagen, configuración, workspace y skills MCP
                 (jarvis-rag, jarvis-email, jarvis-calendar, jarvis-pm, jarvis-office)
infra/           Arranque de los contenedores (init, OpenProject, LiveSync, Tailscale...)
scripts/         configure-mail, configure-telegram, check-integrations, select-models...
docs/            Documentación
tests/           Pruebas
```

## Desarrollo

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```

## Contribuir

Ver `CONTRIBUTING.md`. Licencia MIT (`LICENSE`).
