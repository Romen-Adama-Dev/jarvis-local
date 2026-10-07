"""Operaciones con PDF para Jarvis con `printcraft-cli` (PrintCraft,
github.com/storytold/printcraft): unir, dividir, extraer, borrar y girar páginas, proteger
con contraseña, formularios, marca de agua y reducir el tamaño.

Cada operación copia los PDF de entrada a un directorio temporal, ejecuta un guion de
`printcraft-cli run --script` encerrado en ese directorio (`--root`) y mueve el resultado
al outbox. Los originales nunca se modifican.
"""

import datetime
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from packages.core.errors import JarvisError, NotFoundError, ValidationFailedError
from packages.office import safe_filename

__all__ = [
    "PdfToolError",
    "combine",
    "compress",
    "edit_pages",
    "extract_pages",
    "form",
    "media_reply_many",
    "parse_pages",
    "protect",
    "resolve_pdf",
    "split",
    "watermark",
]

PRINTCRAFT_CLI = os.environ.get("PRINTCRAFT_CLI", "printcraft-cli")
TIMEOUT_SECONDS = 180
MAX_BYTES = 100 * 1024 * 1024
# Telegram agrupa como mucho 10 adjuntos; más partes van en un ZIP.
MAX_MEDIA_FILES = 10


class PdfToolError(JarvisError):
    code = "pdf_tool_error"
    status_code = 422


# --- Ficheros de entrada ---------------------------------------------------------------


def _stored_stem(path: Path) -> str:
    """OpenClaw guarda los adjuntos como `[input-]<nombre saneado>---<uuid>.<ext>`."""
    return path.stem.removeprefix("input-").split("---", 1)[0]


def _find_by_name(name: str, roots: Sequence[Path]) -> Path | None:
    wanted = Path(name)
    wanted_stem = re.sub(r"[^A-Za-z0-9._-]", "_", wanted.stem)
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.pdf"):
            stored = _stored_stem(path)
            truncated = len(stored) >= 8 and wanted_stem.startswith(stored)
            if path.name == wanted.name or (stored and (stored == wanted_stem or truncated)):
                matches.append(path)
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime).resolve()


def resolve_pdf(name: str, roots: Sequence[Path]) -> Path:
    """Ruta absoluta o nombre de un PDF recibido por el chat o creado antes por Jarvis
    (outbox), siempre dentro de `roots`."""
    raw = html.unescape(name.strip())
    if not raw:
        raise ValidationFailedError("Falta el nombre del PDF.")
    candidate = Path(raw).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else _find_by_name(raw, roots)
    if path is None:
        raise NotFoundError(f"No encuentro ningún PDF recibido con el nombre «{name}».")
    if not any(path.is_relative_to(root.resolve()) for root in roots):
        raise ValidationFailedError(f"No puedo usar esa ruta: {name}.")
    if not path.is_file():
        raise NotFoundError(f"No existe el archivo «{name}».")
    if path.suffix.lower() != ".pdf":
        raise ValidationFailedError(f"«{path.name}» no es un PDF.")
    if path.stat().st_size > MAX_BYTES:
        raise ValidationFailedError(f"«{path.name}» pasa de {MAX_BYTES // 1024**2} MiB.")
    return path


def parse_pages(spec: str, page_count: int) -> list[int]:
    """«3-5, 8» → [3, 4, 5, 8], en el orden pedido y sin repetir; «todas» → todas."""
    text = spec.strip().lower()
    if text in {"todas", "todo", "all", "*"}:
        return list(range(1, page_count + 1))
    pages: list[int] = []
    text = re.sub(r"\s*(-|al|a)\s*(?=\d)", "-", text)  # «3 - 5», «3 a 5», «3 al 5»
    for part in re.split(r"[,;\sy]+", text):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValidationFailedError(f"No entiendo las páginas «{spec}». Ejemplo: «3-5, 8».")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        step = 1 if last >= first else -1
        for page in range(first, last + step, step):
            if not 1 <= page <= page_count:
                raise ValidationFailedError(
                    f"La página {page} no existe: el PDF tiene {page_count} páginas."
                )
            if page not in pages:
                pages.append(page)
    if not pages:
        raise ValidationFailedError("Indica qué páginas: por ejemplo «3-5, 8».")
    return pages


# --- printcraft-cli --------------------------------------------------------------------


def _error_message(stderr: str, workdir: Path) -> str:
    line = next((x for x in reversed(stderr.strip().splitlines()) if x.strip()), "")
    line = re.sub(r"^printcraft-cli:\s*(step \d+ \(\w+\):\s*)?(\w+:\s*)?", "", line)
    line = line.replace(f"{workdir}/", "").replace(str(workdir), "")
    if "protected by a password" in line:
        return "El PDF tiene contraseña: no puedo abrirlo."
    if match := re.search(r"page (\d+) is out of range: the document has (\d+) pages", line):
        return f"La página {match[1]} no existe: el PDF tiene {match[2]} páginas."
    return f"PrintCraft no pudo hacerlo: {line or 'error desconocido'}."


def _json_stream(text: str) -> list[dict[str, Any]]:
    """`run --script` escribe un objeto JSON por paso, uno detrás de otro."""
    decoder = json.JSONDecoder()
    results: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        results.append(value)
    return results


def _run(steps: list[dict[str, Any]], workdir: Path) -> list[dict[str, Any]]:
    script = workdir / "steps.json"
    script.write_text(json.dumps(steps), encoding="utf-8")
    try:
        proc = subprocess.run(
            [PRINTCRAFT_CLI, "run", "--script", script.name, "--root", str(workdir)],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PdfToolError("printcraft-cli no está instalado en el servidor.") from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfToolError(f"PrintCraft tardó más de {TIMEOUT_SECONDS} s y se canceló.") from exc
    finally:
        script.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise PdfToolError(_error_message(proc.stderr, workdir))
    return _json_stream(proc.stdout)


def _stage(paths: Sequence[Path], workdir: Path) -> list[str]:
    names = []
    for index, path in enumerate(paths, start=1):
        name = f"in-{index}.pdf"
        shutil.copyfile(path, workdir / name)
        names.append(name)
    return names


def _page_count(workdir: Path, name: str) -> int:
    opened = _run([{"tool": "doc_open", "args": {"path": name}}], workdir)
    return int(opened[0]["pages"])


# --- Resultados ------------------------------------------------------------------------


def _out_path(out_dir: Path, source: Path, label: str, suffix: str = ".pdf") -> Path:
    # Sin la hora de una operación anterior: «x-unido-0950» → «x-unido-protegido-0951».
    stem = re.sub(r"-\d{4}(-\d+)?$", "", safe_filename(_stored_stem(source), max_len=40))
    stamp = datetime.datetime.now().strftime("%H%M")
    base = f"{stem}-{label}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{base}{suffix}"
    counter = 2
    while path.exists():
        path = out_dir / f"{base}-{counter}{suffix}"
        counter += 1
    return path


def _deliver(produced: Path, out_dir: Path, source: Path, label: str) -> Path:
    if not produced.is_file():
        raise PdfToolError("PrintCraft no generó el archivo.")
    target = _out_path(out_dir, source, label)
    shutil.move(produced, target)
    return target


def media_reply_many(paths: Sequence[Path], what: str) -> str:
    """Como `packages.office.media_reply`, con una línea `MEDIA:` por archivo."""
    names = ", ".join(p.name for p in paths)
    return "\n".join(
        [
            f"{what}: {names}.",
            "Para enviar los archivos por el chat, termina tu respuesta con estas líneas "
            "EXACTAS, cada una sola en su línea, sin comillas, negritas ni bloque de código:",
            *(f"MEDIA:{p}" for p in paths),
        ]
    )


# --- Operaciones -----------------------------------------------------------------------


def combine(sources: Sequence[Path], out_dir: Path) -> Path:
    if len(sources) < 2:
        raise ValidationFailedError("Para unir hacen falta al menos dos PDF.")
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        names = _stage(sources, workdir)
        _run([{"tool": "doc_combine", "args": {"paths": names, "out": "out.pdf"}}], workdir)
        return _deliver(workdir / "out.pdf", out_dir, sources[0], "unido")


def split(source: Path, every: int, out_dir: Path) -> list[Path]:
    if every < 1:
        raise ValidationFailedError("`every` tiene que ser 1 o más páginas por parte.")
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        pages = _page_count(workdir, name)
        if every >= pages:
            raise ValidationFailedError(
                f"El PDF tiene {pages} páginas: con partes de {every} no hay nada que dividir."
            )
        steps = [
            {"tool": "doc_open", "args": {"path": name}},
            {"tool": "doc_split", "args": {"doc": 1, "every": every, "out_dir": "partes"}},
        ]
        _run(steps, workdir)
        parts = sorted(
            (workdir / "partes").glob("*.pdf"),
            key=lambda p: int(m[1]) if (m := re.search(r"(\d+)\.pdf$", p.name)) else 0,
        )
        if not parts:
            raise PdfToolError("PrintCraft no generó ninguna parte.")
        if len(parts) <= MAX_MEDIA_FILES:
            return [
                _deliver(part, out_dir, source, f"parte-{index}")
                for index, part in enumerate(parts, start=1)
            ]
        archive = _out_path(out_dir, source, "partes", suffix=".zip")
        stem = archive.stem.rsplit("-", 1)[0]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for index, part in enumerate(parts, start=1):
                zf.write(part, f"{stem}-{index:03d}.pdf")
        return [archive]


def extract_pages(source: Path, pages: str, out_dir: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        selected = parse_pages(pages, _page_count(workdir, name))
        steps = [
            {"tool": "doc_open", "args": {"path": name}},
            {"tool": "page_extract", "args": {"doc": 1, "pages": selected, "out": "out.pdf"}},
        ]
        _run(steps, workdir)
        return _deliver(workdir / "out.pdf", out_dir, source, "paginas")


def edit_pages(source: Path, delete: str, rotate: str, degrees: int, out_dir: Path) -> Path:
    if not delete.strip() and not rotate.strip():
        raise ValidationFailedError("Indica qué páginas borrar (`delete`) o girar (`rotate`).")
    if degrees % 90 or degrees % 360 == 0:
        raise ValidationFailedError("El giro tiene que ser 90, 180 o 270 grados (o -90).")
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        count = _page_count(workdir, name)
        steps: list[dict[str, Any]] = [{"tool": "doc_open", "args": {"path": name}}]
        # Primero el giro: los números de página son los del PDF original.
        if rotate.strip():
            to_rotate = parse_pages(rotate, count)
            steps.append(
                {"tool": "page_rotate", "args": {"doc": 1, "pages": to_rotate, "degrees": degrees}}
            )
        if delete.strip():
            to_delete = parse_pages(delete, count)
            if len(to_delete) >= count:
                raise ValidationFailedError("No puedo borrar todas las páginas del PDF.")
            steps.append({"tool": "page_delete", "args": {"doc": 1, "pages": to_delete}})
        steps.append({"tool": "doc_save", "args": {"doc": 1, "path": "out.pdf"}})
        _run(steps, workdir)
        return _deliver(workdir / "out.pdf", out_dir, source, "editado")


def protect(source: Path, password: str, out_dir: Path) -> Path:
    if len(password) < 4:
        raise ValidationFailedError("La contraseña tiene que tener al menos 4 caracteres.")
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        steps = [
            {"tool": "doc_open", "args": {"path": name}},
            {"tool": "doc_protect", "args": {"doc": 1, "open_password": password}},
            {"tool": "doc_save", "args": {"doc": 1, "path": "out.pdf"}},
        ]
        _run(steps, workdir)
        return _deliver(workdir / "out.pdf", out_dir, source, "protegido")


def form(source: Path, values: dict[str, Any] | None, out_dir: Path) -> str | Path:
    """Sin `values`: los campos del formulario como texto. Con `values`: el PDF relleno."""
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        opened = {"tool": "doc_open", "args": {"path": name}}
        if not values:
            result = _run([opened, {"tool": "form_fields", "args": {"doc": 1}}], workdir)
            return _describe_fields(result[-1])
        steps = [
            opened,
            {"tool": "form_fill", "args": {"doc": 1, "values": values}},
            {"tool": "doc_save", "args": {"doc": 1, "path": "out.pdf"}},
        ]
        _run(steps, workdir)
        return _deliver(workdir / "out.pdf", out_dir, source, "relleno")


def _describe_fields(result: dict[str, Any] | list[Any]) -> str:
    fields = result.get("fields", []) if isinstance(result, dict) else result
    if not fields:
        return "El PDF no tiene campos de formulario."
    lines = [f"El formulario tiene {len(fields)} campos (nombre · tipo · valor actual):"]
    for field in fields:
        options = field.get("options") or []
        extra = f" · opciones: {', '.join(map(str, options))}" if options else ""
        value = field.get("value")
        lines.append(
            f"- {field.get('name')} · {field.get('type')} · "
            f"{'vacío' if value in (None, '', []) else value}{extra}"
        )
    return "\n".join(lines)


def watermark(source: Path, text: str, out_dir: Path) -> Path:
    if not text.strip():
        raise ValidationFailedError("Falta el texto de la marca de agua.")
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        steps = [
            {"tool": "doc_open", "args": {"path": name}},
            {"tool": "doc_watermark", "args": {"doc": 1, "text": text.strip()}},
            {"tool": "doc_save", "args": {"doc": 1, "path": "out.pdf"}},
        ]
        _run(steps, workdir)
        return _deliver(workdir / "out.pdf", out_dir, source, "marca")


def compress(source: Path, out_dir: Path) -> tuple[Path | None, int, int]:
    """Copia más pequeña (como «Reducir tamaño» de Acrobat). Devuelve (ruta o None si no
    se gana nada, bytes antes, bytes después)."""
    before = source.stat().st_size
    with tempfile.TemporaryDirectory(prefix="jarvis-pdf-") as tmp:
        workdir = Path(tmp)
        (name,) = _stage([source], workdir)
        steps = [
            {"tool": "doc_open", "args": {"path": name}},
            {"tool": "doc_reduce", "args": {"doc": 1, "path": "out.pdf"}},
        ]
        _run(steps, workdir)
        produced = workdir / "out.pdf"
        after = produced.stat().st_size if produced.is_file() else before
        if after >= before * 0.95:
            return None, before, after
        return _deliver(produced, out_dir, source, "reducido"), before, after
