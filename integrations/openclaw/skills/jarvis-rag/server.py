import os
import shutil
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

JARVIS_API_URL = os.environ.get("JARVIS_API_URL", "http://127.0.0.1:8000").rstrip("/")
JARVIS_API_INTERNAL_TOKEN = os.environ["JARVIS_API_INTERNAL_TOKEN"]
JARVIS_DATA_ROOT = Path(os.environ.get("JARVIS_DATA_ROOT", "/srv/jarvis"))

mcp = FastMCP("jarvis-rag")

_client = httpx.Client(
    base_url=JARVIS_API_URL,
    headers={"Authorization": f"Bearer {JARVIS_API_INTERNAL_TOKEN}"},
    timeout=180.0,
)


def _format_answer(data: dict) -> str:
    if data.get("insufficient_evidence"):
        return data.get("warning") or "No hay evidencia suficiente en la documentación indexada."

    lines = [data["answer"], "", "Fuentes:"]
    for source in data.get("sources", []):
        location = f"pág. {source['page']}" if source.get("page") else (source.get("section") or "")
        lines.append(f"- {source['filename']} ({location}) [confianza {data['confidence']:.2f}]")
    return "\n".join(lines)


@mcp.tool()
def jarvis_ask(query: str) -> str:
    """Consulta el RAG de Jarvis usando Ollama (modo normal, rápido)."""
    response = _client.post("/v1/rag/query", json={"query": query})
    response.raise_for_status()
    return _format_answer(response.json())


@mcp.tool()
def jarvis_deep(query: str) -> str:
    """Consulta el RAG de Jarvis en modo profundo (AirLLM, para tareas sin urgencia)."""
    response = _client.post("/v1/rag/deep-query", json={"query": query})
    response.raise_for_status()
    return _format_answer(response.json())


@mcp.tool()
def jarvis_status() -> str:
    """Consulta la salud de Jarvis API y sus dependencias (Postgres, Redis, Qdrant, Ollama, AirLLM)."""
    health = _client.get("/health").json()
    ready = _client.get("/ready").json()
    lines = [f"API: {health['status']} (v{health['version']})", f"Listo: {ready['ready']}"]
    for dep in ready["dependencies"]:
        marker = "OK" if dep["healthy"] else "FALLO"
        lines.append(f"- {dep['name']}: {marker} {dep.get('detail', '')}".rstrip())
    return "\n".join(lines)


@mcp.tool()
def jarvis_models() -> str:
    """Lista los modelos de inferencia locales disponibles."""
    response = _client.get("/v1/models")
    response.raise_for_status()
    models = response.json()["models"]
    if not models:
        return "No hay modelos disponibles todavía."
    return "\n".join(
        f"- {m['name']} ({m['provider']}, tools={m['supports_tools']})" for m in models
    )


@mcp.tool()
def jarvis_disk() -> str:
    """Consulta el espacio de disco usado por Jarvis en /srv/jarvis."""
    usage = shutil.disk_usage(JARVIS_DATA_ROOT)
    gib = 1024**3
    return (
        f"{JARVIS_DATA_ROOT}: {usage.used / gib:.1f} GiB usados de "
        f"{usage.total / gib:.1f} GiB ({usage.used / usage.total * 100:.0f}%), "
        f"{usage.free / gib:.1f} GiB libres."
    )


@mcp.tool()
def jarvis_jobs() -> str:
    """Lista los trabajos de indexación/inferencia activos o recientes."""
    response = _client.get("/v1/jobs")
    response.raise_for_status()
    jobs = response.json()["jobs"]
    active = [j for j in jobs if j["status"] not in {"completed", "failed", "cancelled"}]
    if not active:
        return "No hay trabajos activos."
    return "\n".join(f"- {j['id']} [{j['job_type']}] {j['status']} ({j['progress']}%)" for j in active)


@mcp.tool()
def jarvis_cancel_job(job_id: str) -> str:
    """Cancela un trabajo por su identificador."""
    response = _client.post(f"/v1/jobs/{job_id}/cancel")
    response.raise_for_status()
    job = response.json()
    return f"Trabajo {job['id']} -> {job['status']}"


if __name__ == "__main__":
    mcp.run()
