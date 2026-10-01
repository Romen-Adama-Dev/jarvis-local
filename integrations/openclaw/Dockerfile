# Imagen del gateway OpenClaw de Jarvis para docker compose: Node 24 + OpenClaw fijado,
# las skills MCP de Python del repo (con su venv), whisper.cpp (STT en CPU) y Piper (TTS
# es_ES). La configuración no se hornea: docker-entrypoint.sh la genera en cada arranque
# desde integrations/openclaw/config/openclaw.template.json y .env. Contexto: raíz del repo.
ARG OPENCLAW_VERSION=2026.9.4

FROM debian:bookworm-slim AS whisper
ARG WHISPER_CPP_TAG=v1.8.3
# x86-64-v3 (AVX2): cualquier servidor de la última década. Pon OFF para CPUs antiguas.
ARG WHISPER_AVX2=ON
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone -q --depth 1 --branch "${WHISPER_CPP_TAG}" https://github.com/ggml-org/whisper.cpp.git /src \
    && cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
        -DGGML_CUDA=OFF -DGGML_NATIVE=OFF -DGGML_AVX=${WHISPER_AVX2} -DGGML_AVX2=${WHISPER_AVX2} \
        -DGGML_F16C=${WHISPER_AVX2} -DGGML_FMA=${WHISPER_AVX2} -DWHISPER_BUILD_TESTS=OFF \
    && cmake --build /build --config Release -j"$(nproc)" --target whisper-cli

FROM debian:bookworm-slim AS voice-models
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /models/whisper /models/piper \
    && curl -fsSL -o /models/whisper/ggml-small-q5_1.bin \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin \
    && for ext in onnx onnx.json; do \
        curl -fsSL -o "/models/piper/es_ES-davefx-medium.${ext}" \
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.${ext}"; \
    done

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && uv venv /opt/piper \
    && VIRTUAL_ENV=/opt/piper uv pip install piper-tts

FROM node:24-bookworm-slim AS node

# CLI de Tailscale para `tailscale serve`/`whois` contra el tailscaled del servicio
# tailscale (misma versión que su imagen en compose.yml).
FROM tailscale/tailscale:v1.102.3 AS tailscale

FROM python:3.12-slim-bookworm
ARG OPENCLAW_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g "openclaw@${OPENCLAW_VERSION}" \
    && npm cache clean --force

COPY --from=whisper /build/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=tailscale /usr/local/bin/tailscale /usr/local/bin/tailscale
COPY --from=voice-models /models /srv/jarvis/models
COPY --from=app /opt/piper /opt/piper
COPY --from=app /app /app

# HOME escribible por cualquier UID: compose puede correr el contenedor con el UID del
# dueño de un directorio de estado ya existente (JARVIS_UID). El estado de OpenClaw
# (~/.openclaw) es un volumen.
RUN useradd --uid 1000 --create-home --home-dir /home/jarvis jarvis \
    && install -m 755 /app/integrations/openclaw/config/jarvis-tts /opt/piper/bin/jarvis-tts \
    && mkdir -p /home/jarvis/.local/bin /home/jarvis/.openclaw \
    && ln -s /opt/piper/bin/jarvis-tts /home/jarvis/.local/bin/jarvis-tts \
    && install -m 755 /app/integrations/openclaw/config/jarvis-admin /usr/local/bin/jarvis-admin \
    && chown -R jarvis:jarvis /home/jarvis \
    && chmod 1777 /home/jarvis /home/jarvis/.local /home/jarvis/.local/bin

ENV HOME=/home/jarvis \
    NODE_OPTIONS=--max-old-space-size=8192 \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
USER jarvis
WORKDIR /home/jarvis
ENTRYPOINT ["/app/integrations/openclaw/docker-entrypoint.sh"]
