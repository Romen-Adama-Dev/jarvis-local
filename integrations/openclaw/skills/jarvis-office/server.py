"""Servidor MCP `jarvis-office`: documentos ofimáticos reales (Excel, Word, PowerPoint y
OpenDocument) a partir de contenido que redacta el propio agente.

A diferencia de `jarvis_generate_doc` (jarvis-rag), aquí no se consulta el RAG: el modelo
escribe el contenido (o lo copia de otra herramienta) y este servidor solo le da formato.
Los ficheros se dejan en el outbox del workspace para enviarlos por el chat con `MEDIA:`.
"""

import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from packages.core.errors import JarvisError  # noqa: E402
from packages.office import FORMATS, build_document, media_reply, parse_blocks  # noqa: E402

JARVIS_OUTBOX_DIR = Path(
    os.environ.get("JARVIS_OUTBOX_DIR", Path.home() / ".openclaw" / "workspace-jarvis" / "outbox")
)

mcp = FastMCP("jarvis-office")


@mcp.tool()
def jarvis_make_document(
    format: str, title: str, blocks: list[dict[str, Any]], filename: str = ""
) -> str:
    """Crea un documento ofimático REAL con formato: `format` = xlsx (Excel), docx (Word),
    pptx (PowerPoint), ods, odt u odp (LibreOffice/OpenOffice). Úsala cuando el usuario
    pida «hazme un Excel/Word/PowerPoint con…», un acta, una tabla, un presupuesto o una
    presentación con contenido que ya tienes; para un documento fundamentado en la
    documentación indexada usa jarvis_generate_doc.

    `blocks` es la lista de contenido, en orden:
    - {"type": "heading", "text": "Objetivos", "level": 1}  (level 1-3; en pptx/odp cada
      heading de nivel 1 es una diapositiva nueva)
    - {"type": "paragraph", "text": "Texto con **negrita**"}
    - {"type": "bullets", "items": ["punto 1", "punto **2**"]}
    - {"type": "table", "name": "Costes", "columns": ["Partida", "Horas", "Importe"],
       "rows": [["Diseño", 10, 1200.5], ["Pruebas", 5, 600]], "total": true}
      Números como números (1200.5, no "1.200,50 €"). En xlsx/ods cada tabla es una hoja
      (`name` = nombre de la hoja), con cabecera en negrita, filtros y la fila «Total» con
      fórmulas SUM si `total` es true; se admiten fórmulas simples como "=B2*C2".

    Devuelve una línea `MEDIA:<ruta>`: termina tu respuesta con esa línea exacta para que
    el archivo llegue por el chat. `filename` opcional (sin extensión)."""
    try:
        parsed = parse_blocks(blocks)
        path = build_document(format, title, parsed, JARVIS_OUTBOX_DIR, filename=filename)
    except JarvisError as exc:
        return f"No se pudo crear el documento: {exc.message} Formatos: {', '.join(FORMATS)}."
    return media_reply(path, "Documento")


if __name__ == "__main__":
    mcp.run()
