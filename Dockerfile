FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libmagic1 \
        pandoc \
        texlive-xetex \
        texlive-latex-recommended \
        texlive-fonts-recommended \
        lmodern \
        fonts-dejavu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --create-home jarvis \
    && mkdir -p /srv/jarvis/data /srv/jarvis/documents /srv/jarvis/models \
        /srv/jarvis/backups /srv/jarvis/logs \
    && chown -R jarvis:jarvis /srv/jarvis

WORKDIR /app
COPY --from=builder --chown=jarvis:jarvis /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER jarvis

ENTRYPOINT ["/app/infra/docker/entrypoint.sh"]
CMD ["api"]
