# Jarvis Local

Asistente de IA privado y local: RAG sobre documentación propia, memoria por usuario, control por Telegram y Microsoft Teams vía OpenClaw, agente MCP (correo por IMAP/SMTP o Microsoft Graph, calendario por CalDAV o Graph, y documentos generados que se envían por el chat) e inferencia con Ollama (habitual) y AirLLM (`/deep`, modelos grandes). El RAG y la inferencia son 100% locales: ningún documento, embedding, prompt o respuesta sale del servidor hacia APIs de modelos en la nube. Telegram y Teams son los transportes de conversación; el agente de correo/calendario sí sale además al proveedor configurado (servidor IMAP/SMTP/CalDAV o Microsoft Graph) con los datos propios de esa integración (ver `docs/EMAIL.md` y `docs/CALENDAR.md`).

## Arranque rápido

```bash
cp .env.example .env   # rellena TELEGRAM_BOT_TOKEN y TELEGRAM_AUTHORIZED_USER_IDS
docker compose up -d
```

Requiere Docker con Compose v2.30+ y, para GPU, NVIDIA Container Toolkit. Los secretos y el modelo adecuado a tu GPU se generan solos en el primer arranque. Detalles en `docs/DOCKER.md`; para abrir el panel de OpenClaw desde el móvil o el portátil por Tailscale, `docs/ACCESO-REMOTO.md`.

Ver `docs/ARCHITECTURE.md` para el diseño completo y `docs/INSTALL.md` para la instalación reproducible desde cero. La elección automática de modelo Ollama según la VRAM disponible está en `docs/MODELS.md` (`scripts/select-models`).

## Estado del proyecto

En construcción por fases. Ver `docs/ACCEPTANCE.md` para el estado de los criterios de aceptación y `docs/ROADMAP.md` para el plan de evolución.

**Capacidades del agente (Fase 3, en integración):**

* **Calendario** (`docs/CALENDAR.md`) — consulta de eventos y flujo borrador→confirmación para crear reuniones, sobre CalDAV (Nextcloud, iCloud, Fastmail...) o Microsoft Graph.
* **Correo** (`docs/EMAIL.md`) — lectura de bandeja y flujo borrador→confirmación para enviar correo, con documentos generados adjuntos, sobre IMAP/SMTP (cualquier proveedor) o Microsoft Graph.
* **Generación de documentos** (`docs/DOCGEN.md`) — resúmenes, DAFO y planes fundamentados en el RAG, exportables a Markdown/DOCX/PDF/PPTX y enviados por Telegram.
* **Microsoft Teams** (`docs/TEAMS.md`) — segundo canal de interacción junto a Telegram.

Correo y calendario se configuran con `scripts/configure-mail` (IMAP/SMTP + CalDAV con contraseña de aplicación, sin Azure) o, para Microsoft 365, con `MAIL_PROVIDER=msgraph`/`CALENDAR_PROVIDER=msgraph` y `scripts/configure-msgraph` (`docs/MSGRAPH.md`). Sin configurar responden con un error `provider_unavailable` explícito en vez de fallar.

## Contribuir

Ver `CONTRIBUTING.md`. Proyecto bajo licencia MIT (`LICENSE`).

## Estructura

```text
apps/            API (FastAPI) y worker (arq)
packages/        Dominio: core, security, documents, rag, inference, msgraph, imapsmtp, caldavcal, docgen
services/airllm/ Microservicio AirLLM independiente
integrations/    Skills de OpenClaw: jarvis-rag, jarvis-calendar, jarvis-email
infra/           Docker Compose, unidades systemd, monitorización, nginx
scripts/         Automatización idempotente (bootstrap, instalación, backups...)
docs/            Documentación obligatoria
tests/           Unitarios, integración, API, evaluación RAG
```

## Arranque rápido

```bash
scripts/quickstart
```

Clona y arranca: prepara `.env` (genera los secretos locales que faltan,
detecta la GPU y elige el modelo Ollama según `docs/MODELS.md`) y levanta
la aplicación (API + worker, empaquetada en una única imagen que aplica
migraciones y arranca sola) junto a Qdrant, PostgreSQL y Redis. Ollama (y
opcionalmente AirLLM) corren nativos por GPU; ver `docs/DOCKER.md` para el
diseño de ese perfil, sus límites actuales, y la advertencia de no mezclarlo
con el despliegue systemd en la misma máquina. Ver `docs/INSTALL.md` para el
camino completo de despliegue reproducible (bare-metal, systemd).

## Requisitos

* Ubuntu 26.04 LTS
* Python 3.12 (gestionado por `uv`)
* Docker Engine + Docker Compose
* GPU NVIDIA con driver instalado (opcional pero recomendado)

## Desarrollo

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pyright
```
