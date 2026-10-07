"""Archivos que el agente nombra en una herramienta: adjuntos recibidos por el chat o
resultados que ya dejó en el outbox. OpenClaw guarda los adjuntos como
`[input-]<nombre saneado y a veces truncado>---<uuid>.<ext>`, así que el modelo los pasa
por el nombre que vio en `<file name="...">` y aquí se localizan."""

import html
import re
from collections.abc import Collection, Sequence
from pathlib import Path

from packages.core.errors import NotFoundError, ValidationFailedError


def stored_stem(path: Path) -> str:
    """«input-Informe_Q3---0a1b.pdf» → «Informe_Q3»."""
    return path.stem.removeprefix("input-").split("---", 1)[0]


def display_name(path: Path) -> str:
    """Nombre para enseñar o adjuntar, sin el prefijo ni el uuid de OpenClaw."""
    return f"{stored_stem(path) or path.stem}{path.suffix}"


def _find_by_name(name: str, roots: Sequence[Path], suffixes: Collection[str]) -> Path | None:
    wanted = Path(name)
    wanted_stem = re.sub(r"[^A-Za-z0-9._-]", "_", wanted.stem)
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob(f"*{wanted.suffix}" if wanted.suffix else "*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            stored = stored_stem(path)
            truncated = len(stored) >= 8 and wanted_stem.startswith(stored)
            if path.name == wanted.name or (stored and (stored == wanted_stem or truncated)):
                matches.append(path)
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime).resolve()


def resolve_local_file(
    name: str,
    roots: Sequence[Path],
    *,
    suffixes: Collection[str],
    max_bytes: int,
    what: str = "archivo",
) -> Path:
    """Ruta absoluta o nombre de un archivo dentro de `roots`, con una de las extensiones
    `suffixes` (en minúscula, con punto) y como mucho `max_bytes`."""
    raw = html.unescape(name.strip())
    if not raw:
        raise ValidationFailedError(f"Falta el nombre del {what}.")
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else _find_by_name(raw, roots, suffixes)
    if path is None:
        raise NotFoundError(f"No encuentro ningún {what} con el nombre «{name}».")
    if not any(path.is_relative_to(root.resolve()) for root in roots):
        raise ValidationFailedError(f"No puedo usar esa ruta: {name}.")
    if not path.is_file():
        raise NotFoundError(f"No existe el archivo «{name}».")
    if path.suffix.lower() not in suffixes:
        raise ValidationFailedError(f"«{path.name}» no es un {what}.")
    if path.stat().st_size > max_bytes:
        raise ValidationFailedError(f"«{path.name}» pasa de {max_bytes // 1024**2} MiB.")
    return path
