"""Servidor MCP `jarvis-pdf`: operaciones con PDF con PrintCraft (`packages.pdf`): unir,
dividir, extraer, borrar y girar páginas, contraseña, formularios, marca de agua y reducir.

Trabaja con los adjuntos recibidos por el chat y con los PDF que Jarvis ya dejó en el
outbox; el resultado va al outbox para enviarlo con `MEDIA:`. Los originales no se tocan.
"""

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from packages import pdf  # noqa: E402
from packages.core.errors import JarvisError  # noqa: E402
from packages.office import media_reply  # noqa: E402

JARVIS_OUTBOX_DIR = Path(
    os.environ.get("JARVIS_OUTBOX_DIR", Path.home() / ".openclaw" / "workspace-jarvis" / "outbox")
)
JARVIS_DATA_ROOT = Path(os.environ.get("JARVIS_DATA_ROOT", "/srv/jarvis"))
# Los mismos orígenes que jarvis_upload (jarvis-rag) más el outbox, para encadenar
# operaciones («únelos y ponle contraseña»).
PDF_ROOTS = (
    Path.home() / ".openclaw" / "workspace-jarvis" / "media",
    Path.home() / ".openclaw" / "media",
    Path.home() / "jarvis-inbox",
    JARVIS_DATA_ROOT / "documents",
    JARVIS_OUTBOX_DIR,
)

mcp = FastMCP("jarvis-pdf")


def _safely(action: Callable[[], str]) -> str:
    try:
        return action()
    except JarvisError as exc:
        return f"No se pudo: {exc.message}"


def _one(name: str) -> Path:
    return pdf.resolve_pdf(name, PDF_ROOTS)


@mcp.tool()
def jarvis_pdf_combine(files: list[str]) -> str:
    """Une varios PDF en uno, en el orden de `files`: nombres de los adjuntos tal como
    aparecen en `<file name="...">` o de PDF que ya creaste."""
    return _safely(
        lambda: media_reply(pdf.combine([_one(f) for f in files], JARVIS_OUTBOX_DIR), "PDF unido")
    )


@mcp.tool()
def jarvis_pdf_split(file: str, every: int = 1) -> str:
    """Divide un PDF en partes de `every` páginas (1 = una página por archivo)."""

    def run() -> str:
        parts = pdf.split(_one(file), every, JARVIS_OUTBOX_DIR)
        return pdf.media_reply_many(parts, f"PDF dividido en {len(parts)} archivo(s)")

    return _safely(run)


@mcp.tool()
def jarvis_pdf_extract_pages(file: str, pages: str) -> str:
    """PDF nuevo solo con esas páginas y en ese orden: `pages` = "3-5, 8"."""
    return _safely(
        lambda: media_reply(pdf.extract_pages(_one(file), pages, JARVIS_OUTBOX_DIR), "PDF")
    )


@mcp.tool()
def jarvis_pdf_edit_pages(file: str, delete: str = "", rotate: str = "", degrees: int = 90) -> str:
    """Borra páginas (`delete` = "2, 7-9") y/o las gira (`rotate` = "1" o "todas";
    `degrees` 90, 180 o -90). Los números son los del PDF original."""
    return _safely(
        lambda: media_reply(
            pdf.edit_pages(_one(file), delete, rotate, degrees, JARVIS_OUTBOX_DIR), "PDF editado"
        )
    )


@mcp.tool()
def jarvis_pdf_protect(file: str, password: str) -> str:
    """Copia del PDF que pide `password` para abrirse (AES-256). No repitas la contraseña
    en tu respuesta."""
    return _safely(
        lambda: media_reply(pdf.protect(_one(file), password, JARVIS_OUTBOX_DIR), "PDF protegido")
    )


@mcp.tool()
def jarvis_pdf_form(file: str, values: dict[str, Any] | None = None) -> str:
    """Formularios PDF. Sin `values`, lista los campos (nombre, tipo, valor). Con `values`
    ({"Nombre": "Ana", "Acepto": true}, nombres exactos de la lista), devuelve el PDF
    relleno."""

    def run() -> str:
        result = pdf.form(_one(file), values, JARVIS_OUTBOX_DIR)
        return result if isinstance(result, str) else media_reply(result, "Formulario relleno")

    return _safely(run)


@mcp.tool()
def jarvis_pdf_watermark(file: str, text: str) -> str:
    """Marca de agua de texto en diagonal en todas las páginas ("BORRADOR", "CONFIDENCIAL")."""
    return _safely(
        lambda: media_reply(pdf.watermark(_one(file), text, JARVIS_OUTBOX_DIR), "PDF con marca")
    )


@mcp.tool()
def jarvis_pdf_compress(file: str) -> str:
    """Copia más ligera del PDF (imágenes a 150 ppp), p. ej. para mandarlo por correo."""

    def run() -> str:
        path, before, after = pdf.compress(_one(file), JARVIS_OUTBOX_DIR)
        sizes = f"{before / 1024**2:.1f} MB → {after / 1024**2:.1f} MB"
        if path is None:
            return f"No merece la pena: el PDF ya está optimizado ({sizes}). No hay archivo nuevo."
        return media_reply(path, f"PDF reducido ({sizes})")

    return _safely(run)


if __name__ == "__main__":
    mcp.run()
