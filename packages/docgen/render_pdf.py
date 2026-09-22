import os
import shutil
import subprocess
from pathlib import Path

from packages.core.errors import ProviderUnavailableError

_STDERR_TRUNCATE_CHARS = 2000
_TIMEOUT_SECONDS = 180
# El Markdown puede contener texto de documentos de terceros (resúmenes del RAG): sin
# `raw_tex` ni `raw_attribute`, un `\input{/ruta}` sale como texto y no como LaTeX que
# xelatex ejecutaría leyendo ficheros del contenedor.
_MARKDOWN_READER = "markdown-raw_tex-raw_attribute"


def render_pdf_via_pandoc(markdown_path: Path, out_path: Path) -> None:
    if shutil.which("pandoc") is None or shutil.which("xelatex") is None:
        raise ProviderUnavailableError(
            "pandoc/xelatex no están instalados; ejecuta scripts/install-docgen"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "pandoc",
                "--from",
                _MARKDOWN_READER,
                str(markdown_path),
                "-o",
                str(out_path),
                "--pdf-engine=xelatex",
                "--toc",
                "-V",
                "lang=es",
                "-V",
                "geometry:margin=2.5cm",
                "-V",
                "mainfont=DejaVu Serif",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            # Si aun así llegara LaTeX, TeX solo puede abrir ficheros del directorio actual.
            env={**os.environ, "openin_any": "p", "openout_any": "p", "shell_escape": "f"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ProviderUnavailableError("pandoc tardó demasiado en generar el PDF") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")[:_STDERR_TRUNCATE_CHARS]
        raise ProviderUnavailableError(f"pandoc falló al generar el PDF: {stderr}") from exc
