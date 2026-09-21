# Servicio AirLLM (modo /deep, docs/AIRLLM.md) para docker compose: su propio entorno uv
# con torch cu124 (las bibliotecas CUDA vienen en las ruedas de pip; basta el driver del
# host y NVIDIA Container Toolkit). Contexto: services/airllm.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra runtime --no-dev --no-install-project
COPY airllm_service ./airllm_service

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 1000 --create-home jarvis
WORKDIR /app
COPY --from=builder --chown=jarvis:jarvis /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/srv/jarvis/models/airllm/hf \
    HF_HUB_DISABLE_TELEMETRY=1
USER jarvis
EXPOSE 11500
CMD ["sh", "-c", "exec uvicorn airllm_service.app:app --host 127.0.0.1 --port ${AIRLLM_PORT:-11500}"]
