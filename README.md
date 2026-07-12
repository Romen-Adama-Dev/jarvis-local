# Jarvis Local

Asistente de IA privado y local: RAG sobre documentación propia, memoria por usuario, control por Telegram vía OpenClaw, inferencia con Ollama (habitual) y AirLLM (`/deep`, modelos grandes). Ningún documento, embedding, prompt o respuesta sale del servidor hacia APIs de modelos en la nube. Telegram es el único transporte externo.

Ver `docs/ARCHITECTURE.md` para el diseño completo y `docs/INSTALL.md` para la instalación reproducible desde cero.

## Estado del proyecto

En construcción por fases. Ver `docs/ACCEPTANCE.md` para el estado de los criterios de aceptación.

## Estructura

```text
apps/            API (FastAPI) y worker (arq)
packages/        Dominio: core, security, documents, rag, inference
services/airllm/ Microservicio AirLLM independiente
integrations/    Skill jarvis-rag para OpenClaw
infra/           Docker Compose, unidades systemd, monitorización, nginx
scripts/         Automatización idempotente (bootstrap, instalación, backups...)
docs/            Documentación obligatoria
tests/           Unitarios, integración, API, evaluación RAG
```

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
