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
| `livesync` | Memoria de Jarvis en Obsidian del iPhone y el portátil | `docs/OBSIDIAN.md` |
| `vault` | Historial del vault de Obsidian en un repositorio git privado | `docs/MEMORY.md` |

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
* **Documentos generados** desde el RAG (resumen, DAFO, planes) en DOCX/PPTX/PDF
  (`docs/DOCGEN.md`), **voz** local (whisper + Piper), **búsqueda web** con SearXNG y
  **directorio de servicios** con enlaces y estado.

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
                 openproject, imapsmtp, caldavcal, msgraph
services/airllm/ Microservicio AirLLM (modo /deep)
integrations/    OpenClaw: imagen, configuración, workspace y skills MCP
                 (jarvis-rag, jarvis-email, jarvis-calendar, jarvis-pm)
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
