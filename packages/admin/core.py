"""Reglas del servicio `admin` (docs/ADMIN.md), sin dependencias: las usan el servidor del
servicio (imagen docker:cli con python3 del sistema) y los tests.

Jarvis administra con `jarvis-admin`, que siempre pide el botón de aprobación en Telegram.
Aquí va lo que el servicio comprueba por su cuenta, pase lo que pase en esa aprobación:
qué servicios se pueden tocar, qué ramas puede crear, que un cambio del repo no lleve
secretos y que los registros no los enseñen.
"""

import json
import re
from pathlib import Path

# Ramas que Jarvis puede crear en el repo: siempre bajo jarvis/, así nunca toca main ni
# las ramas de otros.
BRANCH_RE = re.compile(r"jarvis/(feat|fix|docs|chore|refactor)-[a-z0-9][a-z0-9-]{1,60}")
# El propio servicio y el aprovisionamiento no se reinician desde el chat.
PROTECTED_SERVICES = frozenset({"admin", "init"})
MAX_LOG_LINES = 200
# Secretos con forma reconocible aunque no estén en .env ni en /run/jarvis.
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),  # token de bot de Telegram
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
)
_SECRET_KEY_RE = re.compile(r"PASS|TOKEN|SECRET|KEY|PASSPHRASE|AUTH", re.IGNORECASE)
MIN_SECRET_LEN = 8


def valid_branch(name: str) -> bool:
    return bool(BRANCH_RE.fullmatch(name))


def check_service(name: str, services: list[str]) -> str | None:
    """Mensaje de error, o None si se puede reiniciar o leer."""
    if name in PROTECTED_SERVICES:
        return f"«{name}» no se gestiona desde el chat."
    if name not in services:
        return f"No hay servicio «{name}». Hay: {', '.join(sorted(services))}."
    return None


def parse_ps(output: str) -> list[dict]:
    """`docker compose ps --format json`: una lista JSON o un objeto por línea, según la
    versión de compose."""
    output = output.strip()
    if not output:
        return []
    if output.startswith("["):
        return json.loads(output)
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def log_lines(requested: int) -> int:
    return max(1, min(requested, MAX_LOG_LINES))


def known_secrets(env_file: Path | None, runtime_dir: Path | None) -> list[str]:
    """Valores secretos del servidor: los de .env con nombre de secreto y los que genera
    init en /run/jarvis. Los más largos primero para que redactar no deje restos."""
    values: set[str] = set()
    if env_file and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            value = value.strip().strip("'\"")
            if sep and _SECRET_KEY_RE.search(key) and len(value) >= MIN_SECRET_LEN:
                values.add(value)
    if runtime_dir and runtime_dir.is_dir():
        for path in runtime_dir.iterdir():
            if path.is_file() and path.name not in {"models.env", "passwd"}:
                value = path.read_text(encoding="utf-8", errors="replace").strip()
                if len(value) >= MIN_SECRET_LEN and "\n" not in value:
                    values.add(value)
    return sorted(values, key=len, reverse=True)


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "***")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("***", text)
    return text


def secrets_in_diff(diff: str, secrets: list[str]) -> list[str]:
    """Archivos del diff que añaden un secreto (conocido o con forma de secreto)."""
    found: list[str] = []
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
            continue
        if not line.startswith("+"):
            continue
        added = line[1:]
        leaks = any(s in added for s in secrets) or any(p.search(added) for p in SECRET_PATTERNS)
        if leaks and current not in found:
            found.append(current)
    return found


FORBIDDEN_PATHS = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|id_[a-z0-9]+|backups/.*)$")


def forbidden_files(paths: list[str]) -> list[str]:
    """Archivos que nunca deben acabar en el repo público, lleven lo que lleven."""
    return [p for p in paths if FORBIDDEN_PATHS.search(p) and not p.endswith(".env.example")]
