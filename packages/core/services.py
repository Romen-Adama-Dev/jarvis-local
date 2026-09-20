"""Directorio de servicios de Jarvis: qué hay, dónde se abre y si está en marcha.

Una sola lista (`CATALOG`) para la herramienta MCP `jarvis_services` (lo pregunta el
usuario por Telegram o en el panel) y para la nota `SERVICIOS.md` del vault de Obsidian,
que se regenera al arrancar OpenClaw. Nunca incluye contraseñas: el vault se sincroniza
con el móvil y con GitHub; en su lugar indica el comando que las muestra en el servidor.

    python -m packages.core.services              # directorio por pantalla
    python -m packages.core.services --vault DIR  # escribe DIR/SERVICIOS.md
"""

import argparse
import datetime
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

_TIMEOUT = 3.0


@dataclass(frozen=True, slots=True)
class Service:
    name: str
    description: str
    port_env: str
    default_port: int
    # Perfil de compose que lo activa (vacío = siempre).
    profile: str = ""
    # Ruta HTTP para comprobar que responde (None = comprobar solo el puerto TCP).
    health_path: str | None = "/"
    # Publicado en el tailnet: puerto HTTPS (443 = la raíz del nombre).
    tailscale_https_port_env: str = ""
    tailscale_https_default: int = 0
    # Ruta útil para abrir en el navegador (p. ej. /docs, /dashboard).
    web_path: str = "/"
    web: bool = True
    credentials: str = ""

    @property
    def port(self) -> int:
        return int(os.environ.get(self.port_env) or self.default_port)

    @property
    def tailscale_port(self) -> int:
        env = self.tailscale_https_port_env
        return int((os.environ.get(env) if env else "") or self.tailscale_https_default)


CATALOG: tuple[Service, ...] = (
    Service(
        "Panel de OpenClaw",
        "Chat con Jarvis, sesiones, canales y configuración del agente",
        "OPENCLAW_GATEWAY_PORT",
        18789,
        profile="",
        tailscale_https_default=443,
        credentials="token del gateway: docker compose exec openclaw cat "
        "/run/jarvis/openclaw_gateway_token",
    ),
    Service(
        "OpenProject",
        "Proyectos, tableros, tickets, Gantt, hitos y riesgos",
        "OPENPROJECT_PORT",
        8090,
        profile="pm",
        health_path="/health_checks/default",
        tailscale_https_port_env="OPENPROJECT_HTTPS_PORT",
        tailscale_https_default=8445,
        credentials="usuario admin; contraseña: docker compose exec openclaw cat "
        "/run/jarvis/openproject_admin_password",
    ),
    Service(
        "Obsidian LiveSync (CouchDB)",
        "Sincronización del vault con el móvil y el portátil (la usa el plugin; "
        "administración en /_utils)",
        "COUCHDB_PORT",
        5984,
        profile="livesync",
        health_path="/_up",
        tailscale_https_port_env="LIVESYNC_HTTPS_PORT",
        tailscale_https_default=8443,
        web_path="/_utils",
        credentials="usuario jarvis; contraseña: docker compose exec openclaw cat "
        "/run/jarvis/couchdb_password",
    ),
    Service(
        "API de Jarvis",
        "RAG, documentos, actas, correo y calendario (documentación interactiva en /docs)",
        "JARVIS_API_PORT",
        8000,
        health_path="/health",
        web_path="/docs",
        credentials="token: docker compose exec openclaw cat /run/jarvis/jarvis_api_internal_token",
    ),
    Service("Ollama", "Modelos de lenguaje locales (GPU)", "OLLAMA_PORT", 11434, web=False),
    Service(
        "Qdrant",
        "Base vectorial del RAG (panel en /dashboard)",
        "QDRANT_PORT",
        6333,
        health_path="/healthz",
        web_path="/dashboard",
    ),
    Service("SearXNG", "Buscador web privado del agente", "SEARXNG_PORT", 8888),
    Service(
        "PostgreSQL",
        "Base de datos de Jarvis y de OpenProject",
        "POSTGRES_PORT",
        5432,
        health_path=None,
        web=False,
        credentials="usuario jarvis; contraseña: docker compose exec openclaw cat "
        "/run/jarvis/postgres_password",
    ),
    Service("Redis", "Cola de trabajos", "REDIS_PORT", 6379, health_path=None, web=False),
    Service(
        "changedetection",
        "Vigilancia de páginas web",
        "CHANGEDETECTION_PORT",
        5000,
        profile="assistant",
    ),
    Service("n8n", "Automatizaciones", "N8N_PORT", 5678, profile="automation"),
    Service("Open WebUI", "Chat directo con Ollama", "WEBUI_PORT", 3080, profile="webui"),
    Service(
        "Prometheus",
        "Métricas",
        "PROMETHEUS_PORT",
        9090,
        profile="monitoring",
        health_path="/-/healthy",
    ),
    Service(
        "Grafana",
        "Paneles de métricas",
        "GRAFANA_PORT",
        3000,
        profile="monitoring",
        health_path="/api/health",
    ),
)


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    service: Service
    up: bool
    local_url: str
    tailnet_url: str


def active_profiles() -> set[str]:
    return {p.strip() for p in os.environ.get("COMPOSE_PROFILES", "").split(",") if p.strip()}


def tailnet_name() -> str:
    path = Path(os.environ.get("TAILSCALE_DNSNAME_FILE", "/var/run/tailscale/dnsname"))
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def tailnet_ip() -> str:
    try:
        out = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5, check=True
        )
        return out.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def _is_up(service: Service) -> bool:
    if service.health_path is None:
        try:
            with socket.create_connection(("127.0.0.1", service.port), timeout=_TIMEOUT):
                return True
        except OSError:
            return False
    try:
        # Cualquier respuesta HTTP (también 401) cuenta como "en marcha".
        httpx.get(f"http://127.0.0.1:{service.port}{service.health_path}", timeout=_TIMEOUT)
        return True
    except httpx.HTTPError:
        return False


def statuses(dnsname: str | None = None) -> list[ServiceStatus]:
    """Servicios activos según COMPOSE_PROFILES, con su estado y sus URLs."""
    profiles = active_profiles()
    dnsname = tailnet_name() if dnsname is None else dnsname
    with_tailscale = bool(dnsname) and "tailscale" in profiles
    result = []
    for service in CATALOG:
        if service.profile and service.profile not in profiles:
            continue
        tailnet_url = ""
        if with_tailscale and service.tailscale_port:
            port = "" if service.tailscale_port == 443 else f":{service.tailscale_port}"
            path = "" if service.web_path == "/" else service.web_path
            tailnet_url = f"https://{dnsname}{port}{path}"
        path = "" if service.web_path == "/" else service.web_path
        scheme = "http://" if service.web else ""
        local_url = f"{scheme}127.0.0.1:{service.port}{path if service.web else ''}"
        result.append(ServiceStatus(service, _is_up(service), local_url, tailnet_url))
    return result


def render_text(items: list[ServiceStatus], *, ip: str = "") -> str:
    """Directorio breve para el chat."""
    remote = [s for s in items if s.tailnet_url]
    local = [s for s in items if not s.tailnet_url]
    lines = ["Desde el PC o el móvil (con Tailscale conectado):"]
    for s in remote:
        icon = "🟢" if s.up else "🔴"
        lines.append(f"{icon} {s.service.name}: {s.tailnet_url}")
    if ip:
        lines.append(f"IP del servidor en el tailnet: {ip}")
    lines.append(
        "Solo en el servidor: NO se abren con la IP ni el nombre de Tailscale; desde el PC, "
        "túnel SSH (ssh -L PUERTO:127.0.0.1:PUERTO <servidor>) y la dirección tal cual:"
    )
    for s in local:
        icon = "🟢" if s.up else "🔴"
        lines.append(f"{icon} {s.service.name}: {s.local_url}")
    return "\n".join(lines)


def render_markdown(items: list[ServiceStatus], *, dnsname: str = "", ip: str = "") -> str:
    """Nota SERVICIOS.md para el vault (sin secretos)."""
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "---",
        "title: Servicios de Jarvis",
        "tags: [jarvis, servicios]",
        "---",
        "",
        "<!-- openclaw:wiki:raw-source -->",
        "",
        "# Servicios de Jarvis",
        "",
        f"Generado automáticamente al arrancar Jarvis ({now}). El estado en vivo se lo "
        "puedes pedir a Jarvis: *«¿qué servicios hay?»*.",
        "",
        "## Desde el PC o el móvil (Tailscale)",
        "",
        "Con Tailscale conectado en el dispositivo:",
        "",
        "| Servicio | Enlace | Para qué | Acceso |",
        "|---|---|---|---|",
    ]
    for s in (x for x in items if x.tailnet_url):
        lines.append(
            f"| {s.service.name} | [{s.tailnet_url}]({s.tailnet_url}) | "
            f"{s.service.description} | {s.service.credentials or '—'} |"
        )
    if dnsname or ip:
        lines += ["", f"Servidor en el tailnet: `{dnsname}`" + (f" (`{ip}`)" if ip else "")]
    lines += [
        "",
        "## Solo dentro del servidor",
        "",
        "Escuchan en `127.0.0.1`. Para abrirlos desde el PC, túnel SSH al servidor y luego la "
        "dirección local en el navegador:",
        "",
        "```bash",
        "ssh -L 8000:127.0.0.1:8000 <servidor>     # p. ej. la API en http://127.0.0.1:8000/docs",
        "```",
        "",
        "| Servicio | Dirección en el servidor | Para qué | Acceso |",
        "|---|---|---|---|",
    ]
    for s in (x for x in items if not x.tailnet_url):
        lines.append(
            f"| {s.service.name} | `{s.local_url}` | {s.service.description} | "
            f"{s.service.credentials or '—'} |"
        )
    lines += [
        "",
        "## Manejarlo desde Telegram",
        "",
        "- *«¿Qué servicios hay?»* — este directorio con el estado en vivo.",
        "- *«¿Cómo va el proyecto X?»*, *«crea la tarea…»* — OpenProject.",
        "- *«Haz el acta de esta reunión»* — actas (adjunta el audio).",
        "- *«¿Qué documentación tengo?»*, preguntas sobre documentos — RAG por empresa y "
        "proyecto.",
        "- *«Estado del servidor»* — salud, modelos y disco.",
        "",
        "Guías en el repo: `docs/DOCKER.md`, `docs/ACCESO-REMOTO.md`, `docs/OPENPROJECT.md`, "
        "`docs/ACTAS.md`, `docs/EMPRESAS.md`, `docs/OBSIDIAN.md`.",
        "",
    ]
    return "\n".join(lines)


def write_vault_note(vault_dir: Path) -> Path | None:
    """Escribe SERVICIOS.md en la raíz del vault si ha cambiado algo más que la fecha."""
    if not vault_dir.is_dir():
        return None
    dnsname = tailnet_name()
    note = vault_dir / "SERVICIOS.md"
    content = render_markdown(statuses(dnsname), dnsname=dnsname, ip=tailnet_ip())

    def body(text: str) -> str:
        return "\n".join(
            line for line in text.splitlines() if "Generado automáticamente" not in line
        )

    if note.is_file() and body(note.read_text(encoding="utf-8")) == body(content):
        return note
    note.write_text(content, encoding="utf-8")
    return note


def main() -> None:
    parser = argparse.ArgumentParser(description=next(iter((__doc__ or "").splitlines()), None))
    parser.add_argument("--vault", type=Path, help="escribe SERVICIOS.md en este vault")
    args = parser.parse_args()
    if args.vault:
        note = write_vault_note(args.vault)
        print(f"Directorio de servicios: {note}" if note else "Sin vault: no se escribe la nota.")
    else:
        print(render_text(statuses(), ip=tailnet_ip()))


if __name__ == "__main__":
    main()
