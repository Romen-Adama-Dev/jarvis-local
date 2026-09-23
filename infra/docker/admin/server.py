"""Servicio `admin` (perfil `admin`, docs/ADMIN.md): lo que Jarvis puede administrar del
servidor, y nada más. Es el único contenedor con el socket de Docker; Jarvis no lo tiene y
llega aquí con `jarvis-admin`, que siempre pide el botón de aprobación en Telegram.

Escucha en 127.0.0.1 con el token que genera init (/run/jarvis/jarvis_admin_token):

    GET  /servicios                         estado de los contenedores
    GET  /registros?servicio=api&lineas=50  últimas líneas del registro, sin secretos
    POST /reiniciar     {"servicio"}        reinicia un servicio
    GET  /repo/estado                       cambios en la copia del repo de Jarvis
    POST /repo/preparar {"rama"}            copia limpia de origin/main en una rama nueva
    POST /repo/pr       {"titulo", "descripcion"}  commit, push y pull request

Los cambios al repo van siempre como pull request: el propietario los revisa y fusiona.
"""

import base64
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_DIR = Path(os.environ.get("JARVIS_REPO_DIR", "/repo"))
sys.path.insert(0, str(REPO_DIR))

from packages.admin import core  # noqa: E402

RUNTIME_DIR = Path(os.environ.get("JARVIS_RUNTIME_DIR", "/run/jarvis"))
CLONE_DIR = Path(os.environ.get("JARVIS_ADMIN_CLONE_DIR", "/state/workspace-jarvis/repo"))
PROJECT = os.environ.get("JARVIS_COMPOSE_PROJECT", "jarvis-local")
GITHUB_REPO = os.environ.get("JARVIS_ADMIN_REPO", "")
GITHUB_TOKEN = os.environ.get("JARVIS_ADMIN_GITHUB_TOKEN", "")
PORT = int(os.environ.get("JARVIS_ADMIN_PORT", "8096"))
# La copia del repo es de Jarvis: la edita con write/edit desde su workspace.
OWNER = f"{os.environ.get('JARVIS_UID', '1000')}:{os.environ.get('JARVIS_GID', '1000')}"
COMMAND_TIMEOUT = 600


class AdminError(Exception):
    pass


def _secrets() -> list[str]:
    extra = [GITHUB_TOKEN] if len(GITHUB_TOKEN) >= core.MIN_SECRET_LEN else []
    return extra + core.known_secrets(REPO_DIR / ".env", RUNTIME_DIR)


def _run(args: list[str], *, cwd: Path | None = None, env: dict | None = None) -> str:
    try:
        done = subprocess.run(
            args,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdminError(f"«{' '.join(args[:3])}…» no terminó en {COMMAND_TIMEOUT} s.") from exc
    output = core.redact((done.stdout + done.stderr).strip(), _secrets())
    if done.returncode != 0:
        raise AdminError(output or f"falló con código {done.returncode}")
    return output


def _compose(*args: str) -> str:
    base = ["docker", "compose", "--project-directory", str(REPO_DIR), "-p", PROJECT]
    return _run([*base, *args])


def _services() -> list[str]:
    return _compose("config", "--services").split()


# --- Servicios --------------------------------------------------------------------------


def servicios() -> str:
    rows = core.parse_ps(_compose("ps", "--all", "--format", "json"))
    lines = [
        f"{r.get('Service')}: {r.get('State')}"
        + (f" ({r.get('Health')})" if r.get("Health") else "")
        for r in sorted(rows, key=lambda r: r.get("Service", ""))
    ]
    return "\n".join(lines) or "No hay contenedores."


def registros(servicio: str, lineas: int) -> str:
    error = core.check_service(servicio, _services())
    if error:
        raise AdminError(error)
    return _compose("logs", "--no-color", "--tail", str(core.log_lines(lineas)), servicio)


def reiniciar(servicio: str) -> str:
    error = core.check_service(servicio, _services())
    if error:
        raise AdminError(error)
    _compose("restart", servicio)
    return f"«{servicio}» reiniciado."


# --- Repositorio ------------------------------------------------------------------------


def _git(*args: str) -> str:
    # El servicio corre como root (socket de Docker) y la copia es del UID de Jarvis.
    return _run(["git", "-c", "safe.directory=*", *args], cwd=CLONE_DIR)


def _auth_env() -> dict:
    """Credenciales solo para esta orden (GIT_CONFIG_*), nunca en .git/config."""
    if not GITHUB_TOKEN:
        return {}
    basic = base64.b64encode(f"x-access-token:{GITHUB_TOKEN}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
    }


def _need_repo() -> None:
    if not GITHUB_REPO:
        raise AdminError("Falta JARVIS_ADMIN_REPO en .env (p. ej. usuario/jarvis-local).")


def repo_preparar(rama: str) -> str:
    _need_repo()
    if not core.valid_branch(rama):
        raise AdminError(
            f"Rama «{rama}» no válida: tiene que ser jarvis/feat-…, jarvis/fix-…, "
            "jarvis/docs-…, jarvis/chore-… o jarvis/refactor-…, en minúsculas y con guiones."
        )
    url = f"https://github.com/{GITHUB_REPO}.git"
    if not (CLONE_DIR / ".git").is_dir():
        CLONE_DIR.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "-q", url, str(CLONE_DIR)], env=_auth_env())
    _run(["git", "-c", "safe.directory=*", "fetch", "-q", "origin", "main"],
         cwd=CLONE_DIR, env=_auth_env())  # fmt: skip
    _git("checkout", "-q", "-B", rama, "origin/main")
    _git("reset", "-q", "--hard", "origin/main")
    _git("clean", "-q", "-fdx")
    _run(["chown", "-R", OWNER, str(CLONE_DIR)])
    return (
        f"Copia limpia de main en la rama {rama}, en {CLONE_DIR.name}/ del workspace. "
        "Edita ahí los archivos y abre la PR con `jarvis-admin repo pr`."
    )


def _changed_files() -> list[str]:
    status = _git("status", "--porcelain", "--untracked-files=all")
    return [line[3:].split(" -> ")[-1] for line in status.splitlines() if line.strip()]


def repo_estado() -> str:
    if not (CLONE_DIR / ".git").is_dir():
        return "Aún no hay copia del repo: empieza con `jarvis-admin repo preparar <rama>`."
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    files = _changed_files()
    listing = "\n".join(f"- {f}" for f in files) or "(sin cambios)"
    return f"Rama {branch}. Archivos cambiados:\n{listing}"


def _github(method: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = core.redact(exc.read().decode(errors="replace")[:500], _secrets())
        raise AdminError(f"GitHub respondió {exc.code}: {detail}") from exc


def repo_pr(titulo: str, descripcion: str) -> str:
    _need_repo()
    if not GITHUB_TOKEN:
        raise AdminError("Falta JARVIS_ADMIN_GITHUB_TOKEN en .env (ver docs/ADMIN.md).")
    if not (CLONE_DIR / ".git").is_dir():
        raise AdminError("No hay copia del repo: empieza con `jarvis-admin repo preparar`.")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not core.valid_branch(branch):
        raise AdminError(
            f"La copia está en «{branch}»: prepara antes una rama con `repo preparar`."
        )
    if not titulo.strip():
        raise AdminError("Falta el título de la PR.")
    files = _changed_files()
    if not files:
        raise AdminError("No hay cambios que proponer.")
    blocked = core.forbidden_files(files)
    if blocked:
        raise AdminError(f"Estos archivos no pueden ir al repo: {', '.join(blocked)}.")
    for path in files:
        _git("add", "--", path)
    leaked = core.secrets_in_diff(_git("diff", "--cached"), _secrets())
    if leaked:
        _git("reset", "-q")
        raise AdminError(f"Cancelado: hay un secreto en {', '.join(leaked)}. Quítalo y repite.")
    _git(
        "-c", "user.name=Jarvis", "-c", "user.email=jarvis@localhost",
        "commit", "-q", "-m", titulo.strip(), "-m", descripcion.strip() or titulo.strip(),
    )  # fmt: skip
    # Sin -f: si la rama ya existe en GitHub (una PR anterior), falla en vez de pisarla.
    _run(["git", "-c", "safe.directory=*", "push", "-q", "origin", f"HEAD:refs/heads/{branch}"],
         cwd=CLONE_DIR, env=_auth_env())  # fmt: skip
    body = (
        f"{descripcion.strip()}\n\n---\nPropuesta de Jarvis desde Telegram, con aprobación "
        "del propietario. Se aplica al fusionarla y redesplegar."
    )
    pr = _github(
        "POST",
        f"/repos/{GITHUB_REPO}/pulls",
        {"title": titulo.strip(), "head": branch, "base": "main", "body": body},
    )
    return f"PR #{pr['number']} abierta: {pr['html_url']}"


# --- HTTP -------------------------------------------------------------------------------


def _token() -> str:
    path = RUNTIME_DIR / "jarvis_admin_token"
    return path.read_text().strip() if path.is_file() else ""


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status: int, text: str) -> None:
        data = json.dumps({"ok": status == 200, "text": text}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        expected = _token()
        given = self.headers.get("Authorization", "").removeprefix("Bearer ")
        return bool(expected) and hmac.compare_digest(given, expected)

    def _handle(self, method: str) -> None:
        if not self._authorized():
            self._reply(401, "Token no válido.")
            return
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        body: dict = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        routes = {
            ("GET", "/servicios"): lambda: servicios(),
            ("GET", "/registros"): lambda: registros(
                query.get("servicio", ""), int(query.get("lineas", "50"))
            ),
            ("POST", "/reiniciar"): lambda: reiniciar(str(body.get("servicio", ""))),
            ("GET", "/repo/estado"): lambda: repo_estado(),
            ("POST", "/repo/preparar"): lambda: repo_preparar(str(body.get("rama", ""))),
            ("POST", "/repo/pr"): lambda: repo_pr(
                str(body.get("titulo", "")), str(body.get("descripcion", ""))
            ),
        }
        action = routes.get((method, url.path))
        if action is None:
            self._reply(404, "Acción desconocida.")
            return
        try:
            self._reply(200, action())
        except (AdminError, ValueError) as exc:
            self._reply(400, str(exc))

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"admin: {self.command} {urlparse(self.path).path}", flush=True)


if __name__ == "__main__":
    print(f"admin: escuchando en 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
