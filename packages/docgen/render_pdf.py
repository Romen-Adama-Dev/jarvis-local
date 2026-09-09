import shutil
import subprocess
from pathlib import Path

from packages.core.errors import ProviderUnavailableError

_STDERR_TRUNCATE_CHARS = 2000


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
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")[:_STDERR_TRUNCATE_CHARS]
        raise ProviderUnavailableError(f"pandoc falló al generar el PDF: {stderr}") from exc
