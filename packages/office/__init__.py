"""Generación de documentos ofimáticos (Excel, Word, PowerPoint y OpenDocument) a partir
de bloques de contenido sencillos (`packages.office.spec`)."""

import datetime
import re
import unicodedata
import uuid
from collections.abc import Callable
from pathlib import Path

from packages.core.errors import ValidationFailedError
from packages.office.ooxml import render_docx, render_pptx, render_xlsx
from packages.office.opendocument import render_odp, render_ods, render_odt
from packages.office.spec import FORMATS, Block, parse_blocks

__all__ = ["FORMATS", "build_document", "media_reply", "parse_blocks", "safe_filename"]

_RENDERERS: dict[str, Callable[[str, list[Block], Path], None]] = {
    "xlsx": render_xlsx,
    "docx": render_docx,
    "pptx": render_pptx,
    "ods": render_ods,
    "odt": render_odt,
    "odp": render_odp,
}
_ALIASES = {"excel": "xlsx", "word": "docx", "powerpoint": "pptx", "ppt": "pptx"}


def normalize_format(fmt: str) -> str:
    value = fmt.strip().lower().lstrip(".")
    value = _ALIASES.get(value, value)
    if value not in FORMATS:
        raise ValidationFailedError(
            f"Formato no soportado «{fmt}». Usa uno de: {', '.join(FORMATS)}."
        )
    return value


def safe_filename(text: str, max_len: int = 50) -> str:
    """Nombre de fichero ASCII sin rutas: «Acta Reunión 1/2» → «acta-reunion-1-2»."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "documento"


def build_document(
    fmt: str,
    title: str,
    blocks: list[Block],
    out_dir: Path,
    *,
    filename: str = "",
) -> Path:
    """Escribe el documento en `out_dir` con un nombre único y devuelve su ruta."""
    fmt = normalize_format(fmt)
    title = title.strip() or "Documento"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    # El modelo a veces incluye la extensión en el nombre («acta.docx»).
    base = re.sub(r"\.(xlsx|docx|pptx|ods|odt|odp)$", "", filename.strip(), flags=re.I)
    stem = f"{safe_filename(base or title)}-{stamp}-{uuid.uuid4().hex[:6]}"
    out_path = out_dir / f"{stem}.{fmt}"
    _RENDERERS[fmt](title, blocks, out_path)
    return out_path


def media_reply(path: Path, what: str) -> str:
    """Respuesta de herramienta para que OpenClaw adjunte el fichero en el chat."""
    return "\n".join(
        [
            f"{what} listo: {path.name}.",
            "Para enviar el archivo por el chat, termina tu respuesta con esta línea EXACTA, "
            "sola en su propia línea, sin comillas, negritas ni bloque de código:",
            f"MEDIA:{path}",
        ]
    )
