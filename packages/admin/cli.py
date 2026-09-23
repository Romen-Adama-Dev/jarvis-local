"""`jarvis-admin`: lo que Jarvis administra, siempre con la aprobación del propietario.

Corre en el contenedor de OpenClaw y no está en la lista blanca de `exec`: cada llamada
pide el botón de aprobación en Telegram con el comando completo a la vista (docs/ADMIN.md).

    jarvis-admin servicios
    jarvis-admin registros SERVICIO [LINEAS]
    jarvis-admin reiniciar SERVICIO
    jarvis-admin repo estado
    jarvis-admin repo preparar jarvis/feat-algo
    jarvis-admin repo pr "Título" "Descripción"
    jarvis-admin op usuarios
    jarvis-admin op usuario-nuevo "Nombre Apellido" correo@ejemplo.com
    jarvis-admin op miembro PROYECTO USUARIO [ROL]

Servicios y repo pasan por el servicio `admin` (el único con Docker); OpenProject, por su
API con la clave del usuario administrador `jarvis`.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("JARVIS_RUNTIME_DIR", "/run/jarvis"))
ADMIN_URL = os.environ.get("JARVIS_ADMIN_URL", "http://127.0.0.1:8096")


def _admin(method: str, path: str, body: dict | None = None) -> str:
    token_file = RUNTIME_DIR / "jarvis_admin_token"
    if not token_file.is_file():
        raise SystemExit("El servicio admin no está activo (perfil `admin`, docs/ADMIN.md).")
    request = urllib.request.Request(
        f"{ADMIN_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token_file.read_text().strip()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=660) as response:
            return json.loads(response.read())["text"]
    except urllib.error.HTTPError as exc:
        raise SystemExit(json.loads(exc.read() or b"{}").get("text", f"Error {exc.code}")) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"El servicio admin no responde ({exc.reason}).") from exc


def _op():
    from packages.openproject.client import OpenProjectClient
    from packages.openproject.config import config_from_env

    config = config_from_env()
    if config is None:
        raise SystemExit("OpenProject no está activo (perfil `pm`).")
    return OpenProjectClient(config)


def _op_command(args: argparse.Namespace) -> str:
    from packages.core.errors import JarvisError

    op = _op()
    try:
        if args.accion == "usuarios":
            return "\n".join(
                f"{u.get('name')} · {u.get('login')} · {u.get('status')}"
                + (" · admin" if u.get("admin") else "")
                for u in op.users()
            )
        if args.accion == "usuario-nuevo":
            user = op.create_user(args.nombre, args.correo)
            return (
                f"Usuario «{user.get('name')}» creado como invitado: OpenProject le envía a "
                f"{args.correo} el enlace para entrar."
            )
        member = op.add_member(args.proyecto, args.usuario, args.rol)
        project = member.get("_links", {}).get("project", {}).get("title", args.proyecto)
        return f"«{args.usuario}» añadido a {project} con el rol {args.rol}."
    except JarvisError as exc:
        raise SystemExit(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis-admin", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("servicios", help="estado de los servicios")
    logs = sub.add_parser("registros", help="últimas líneas del registro de un servicio")
    logs.add_argument("servicio")
    logs.add_argument("lineas", nargs="?", type=int, default=50)
    restart = sub.add_parser("reiniciar", help="reinicia un servicio")
    restart.add_argument("servicio")

    repo = sub.add_parser("repo", help="cambios en el repositorio, como pull request")
    repo_sub = repo.add_subparsers(dest="accion", required=True)
    repo_sub.add_parser("estado")
    prepare = repo_sub.add_parser("preparar")
    prepare.add_argument("rama", help="jarvis/feat-…, jarvis/fix-…, jarvis/docs-…")
    pr = repo_sub.add_parser("pr")
    pr.add_argument("titulo")
    pr.add_argument("descripcion", nargs="?", default="")

    op = sub.add_parser("op", help="administración de OpenProject")
    op_sub = op.add_subparsers(dest="accion", required=True)
    op_sub.add_parser("usuarios")
    new_user = op_sub.add_parser("usuario-nuevo")
    new_user.add_argument("nombre")
    new_user.add_argument("correo")
    member = op_sub.add_parser("miembro")
    member.add_argument("proyecto")
    member.add_argument("usuario")
    member.add_argument("rol", nargs="?", default="Miembro")
    return parser


def run(args: argparse.Namespace) -> str:
    if args.orden == "servicios":
        return _admin("GET", "/servicios")
    if args.orden == "registros":
        query = urllib.parse.urlencode({"servicio": args.servicio, "lineas": args.lineas})
        return _admin("GET", f"/registros?{query}")
    if args.orden == "reiniciar":
        return _admin("POST", "/reiniciar", {"servicio": args.servicio})
    if args.orden == "repo":
        if args.accion == "estado":
            return _admin("GET", "/repo/estado")
        if args.accion == "preparar":
            return _admin("POST", "/repo/preparar", {"rama": args.rama})
        return _admin("POST", "/repo/pr", {"titulo": args.titulo, "descripcion": args.descripcion})
    return _op_command(args)


def main() -> None:
    print(run(build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
