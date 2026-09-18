"""Configuración de OpenProject a partir del entorno y de los secretos de `init`.

La comparten el servidor MCP `jarvis-pm` (contenedor openclaw) y el calendario de la API
(`CALENDAR_PROVIDER=openproject`).
"""

import os
from pathlib import Path

from packages.openproject.client import OpenProjectConfig

RUNTIME_DIR = Path(os.environ.get("JARVIS_RUNTIME_DIR", "/run/jarvis"))
# openclaw monta el socket de tailscaled (con dnsname dentro); el resto, solo el nombre.
_DNSNAME_FILES = (Path("/var/run/tailscale/dnsname"), Path("/var/run/tailscale-info/dnsname"))


def api_key() -> str:
    key = os.environ.get("OPENPROJECT_API_KEY", "")
    if not key and (RUNTIME_DIR / "openproject_api_key").is_file():
        key = (RUNTIME_DIR / "openproject_api_key").read_text().strip()
    return key


def public_url() -> str:
    """URL para abrir en el navegador: por Tailscale si el servidor está en el tailnet."""
    url = os.environ.get("OPENPROJECT_PUBLIC_URL", "")
    if url:
        return url
    for dnsname in _DNSNAME_FILES:
        if dnsname.is_file() and dnsname.read_text().strip():
            port = os.environ.get("OPENPROJECT_HTTPS_PORT", "8445")
            return f"https://{dnsname.read_text().strip()}:{port}"
    return ""


def config_from_env() -> OpenProjectConfig | None:
    """None si OpenProject no está activo (sin clave de API: falta el perfil `pm`)."""
    key = api_key()
    if not key:
        return None
    port = os.environ.get("OPENPROJECT_PORT", "8090")
    return OpenProjectConfig(
        url=os.environ.get("OPENPROJECT_URL", f"http://127.0.0.1:{port}"),
        api_key=key,
        public_url=public_url(),
        owner_login=os.environ.get("OPENPROJECT_OWNER_LOGIN", "admin"),
    )
