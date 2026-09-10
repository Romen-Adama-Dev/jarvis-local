# Jarvis Local

Asistente de IA privado y local: RAG sobre documentación propia, memoria por usuario, control por Telegram y Microsoft Teams vía OpenClaw, agente MCP (correo, calendario y generación de documentos sobre Microsoft Graph) e inferencia con Ollama (habitual) y AirLLM (`/deep`, modelos grandes). El RAG y la inferencia son 100% locales: ningún documento, embedding, prompt o respuesta sale del servidor hacia APIs de modelos en la nube. Telegram y Teams son los transportes de conversación; el agente de correo/calendario sí sale además a Microsoft Graph con los datos propios de esa integración (ver `docs/MSGRAPH.md`).

Ver `docs/ARCHITECTURE.md` para el diseño completo y `docs/INSTALL.md` para la instalación reproducible desde cero.

## Estado del proyecto

En construcción por fases. Ver `docs/ACCEPTANCE.md` para el estado de los criterios de aceptación y `docs/ROADMAP.md` para el plan de evolución.

**Capacidades del agente (Fase 3, en integración):**

* **Calendario** (`docs/CALENDAR.md`) — consulta de eventos y flujo borrador→confirmación para crear reuniones.
* **Correo** (`docs/EMAIL.md`) — lectura de bandeja y flujo borrador→confirmación para enviar correo.
* **Generación de documentos** (`docs/DOCGEN.md`) — DAFO y planes fundamentados en el RAG, exportables a Markdown/DOCX/PDF/PPTX.
* **Microsoft Teams** (`docs/TEAMS.md`) — segundo canal de interacción junto a Telegram.

Calendario y correo comparten una única autenticación OAuth2 contra Microsoft Graph (`docs/MSGRAPH.md`, `scripts/configure-msgraph`); ambas requieren `MSGRAPH_CLIENT_ID`/`MSGRAPH_TENANT_ID` configurados o responden con un error `provider_unavailable` explícito en vez de fallar.

## Contribuir

Ver `CONTRIBUTING.md`. Proyecto bajo licencia MIT (`LICENSE`).

## Estructura

```text
apps/            API (FastAPI) y worker (arq)
packages/        Dominio: core, security, documents, rag, inference, msgraph, docgen
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
detecta la GPU y elige el modelo Ollama según `docs/BENCHMARKS.md`) y levanta
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
