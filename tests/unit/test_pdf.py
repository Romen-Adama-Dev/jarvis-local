import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from packages import pdf
from packages.core.errors import NotFoundError, ValidationFailedError


def _make_pdf(path: Path, pages: int) -> Path:
    """PDF mínimo con una línea de texto por página."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "", "<< /Type /Font /Subtype /Type1 "
               "/BaseFont /Helvetica >>"]  # fmt: skip
    kids = []
    for page in range(1, pages + 1):
        stream = f"BT /F1 18 Tf 72 720 Td (Pagina {page}) Tj ET"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
            f"<< /Font << /F1 3 0 R >> >> /Contents {len(objects)} 0 R >>"
        )
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(out)
    return path


# --- Sin printcraft-cli ----------------------------------------------------------------


def test_parse_pages_ranges_order_and_words():
    assert pdf.parse_pages("3-5, 8", 10) == [3, 4, 5, 8]
    assert pdf.parse_pages("5, 1", 10) == [5, 1]
    assert pdf.parse_pages("2 a 4 y 7", 10) == [2, 3, 4, 7]
    assert pdf.parse_pages("1 al 2; 2", 10) == [1, 2]
    assert pdf.parse_pages("todas", 3) == [1, 2, 3]
    with pytest.raises(ValidationFailedError, match="no existe"):
        pdf.parse_pages("9", 5)
    with pytest.raises(ValidationFailedError, match="No entiendo"):
        pdf.parse_pages("la última", 5)


def test_resolve_pdf_by_attachment_name_and_from_outbox(tmp_path):
    inbound = tmp_path / "media" / "inbound"
    outbox = tmp_path / "outbox"
    inbound.mkdir(parents=True)
    outbox.mkdir()
    stored = _make_pdf(inbound / "input-Informe_Q3---0a1b2c.pdf", 1)
    made = _make_pdf(outbox / "informe-q3-unido-1012.pdf", 1)
    roots = [tmp_path / "media", outbox]
    assert pdf.resolve_pdf("Informe Q3.pdf", roots) == stored.resolve()
    assert pdf.resolve_pdf("informe-q3-unido-1012.pdf", roots) == made.resolve()
    assert pdf.resolve_pdf(str(made), roots) == made.resolve()


def test_resolve_pdf_rejects_outside_roots_and_other_types(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = _make_pdf(tmp_path / "secreto.pdf", 1)
    (root / "notas.txt").write_text("x")
    with pytest.raises(ValidationFailedError, match="No puedo usar esa ruta"):
        pdf.resolve_pdf(str(outside), [root])
    with pytest.raises(ValidationFailedError, match="no es un PDF"):
        pdf.resolve_pdf(str(root / "notas.txt"), [root])
    with pytest.raises(NotFoundError):
        pdf.resolve_pdf("no-existe.pdf", [root])


def test_json_stream_and_error_messages(tmp_path):
    assert pdf._json_stream('{\n "a": 1\n}\n{"b": 2}\n') == [{"a": 1}, {"b": 2}]
    message = pdf._error_message(
        "printcraft-cli: step 2 (page_extract): page 9 is out of range: the document has 5 pages",
        tmp_path,
    )
    assert message == "La página 9 no existe: el PDF tiene 5 páginas."
    message = pdf._error_message(
        "printcraft-cli: step 1 (doc_open): the document is protected by a password", tmp_path
    )
    assert message == "El PDF tiene contraseña: no puedo abrirlo."
    message = pdf._error_message(
        f"printcraft-cli: step 1 (doc_open): {tmp_path}/x.pdf: oops", tmp_path
    )
    assert str(tmp_path) not in message


def test_missing_cli_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "PRINTCRAFT_CLI", str(tmp_path / "no-hay-printcraft"))
    src = _make_pdf(tmp_path / "a.pdf", 2)
    with pytest.raises(pdf.PdfToolError, match="no está instalado"):
        pdf.protect(src, "secreta", tmp_path / "outbox")


def test_media_reply_many_has_one_line_per_file(tmp_path):
    reply = pdf.media_reply_many([tmp_path / "a.pdf", tmp_path / "b.pdf"], "Partes")
    assert reply.splitlines()[-2:] == [f"MEDIA:{tmp_path}/a.pdf", f"MEDIA:{tmp_path}/b.pdf"]


# --- Con printcraft-cli (se saltan si no está instalado) --------------------------------

_CLI = os.environ.get("PRINTCRAFT_CLI") or shutil.which("printcraft-cli")
needs_cli = pytest.mark.skipif(_CLI is None, reason="printcraft-cli no está instalado")


def _info(path: Path, password: str = "") -> dict:
    args = [str(_CLI), "info", str(path)] + (["--password", password] if password else [])
    return json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout)


def _text(path: Path) -> str:
    args = [str(_CLI), "text", str(path)]
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(pdf, "PRINTCRAFT_CLI", str(_CLI))


@needs_cli
def test_combine_split_and_extract(cli, tmp_path):
    outbox = tmp_path / "outbox"
    a = _make_pdf(tmp_path / "input-Contrato---1a2b.pdf", 2)
    b = _make_pdf(tmp_path / "anexo.pdf", 3)
    joined = pdf.combine([a, b], outbox)
    assert joined.parent == outbox and joined.name.startswith("contrato-unido-")
    assert _info(joined)["pages"] == 5
    parts = pdf.split(joined, 2, outbox)
    assert [_info(p)["pages"] for p in parts] == [2, 2, 1]
    assert [p.name.split("-parte-")[1][0] for p in parts] == ["1", "2", "3"]
    assert pdf.protect(joined, "secreta", outbox).name.startswith("contrato-unido-protegido-")
    extracted = pdf.extract_pages(joined, "5, 1-2", outbox)
    assert _text(extracted).split() == ["Pagina", "3", "Pagina", "1", "Pagina", "2"]
    assert a.read_bytes().startswith(b"%PDF-1.4")  # el original no se toca


@needs_cli
def test_split_many_parts_goes_in_a_zip(cli, tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_MEDIA_FILES", 2)
    parts = pdf.split(_make_pdf(tmp_path / "largo.pdf", 4), 1, tmp_path / "outbox")
    assert len(parts) == 1 and parts[0].suffix == ".zip"
    assert len(zipfile.ZipFile(parts[0]).namelist()) == 4


@needs_cli
def test_edit_protect_watermark_and_compress(cli, tmp_path):
    outbox = tmp_path / "outbox"
    src = _make_pdf(tmp_path / "informe.pdf", 4)
    edited = pdf.edit_pages(src, delete="4", rotate="1", degrees=90, out_dir=outbox)
    assert _info(edited)["pages"] == 3
    with pytest.raises(ValidationFailedError, match="todas las páginas"):
        pdf.edit_pages(src, delete="1-4", rotate="", degrees=90, out_dir=outbox)
    locked = pdf.protect(src, "secreta", outbox)
    assert _info(locked, "secreta")["encrypted"]
    with pytest.raises(pdf.PdfToolError, match="contraseña"):
        pdf.watermark(locked, "BORRADOR", outbox)
    marked = pdf.watermark(src, "BORRADOR", outbox)
    assert "BORRADOR" in _text(marked)
    path, before, after = pdf.compress(src, outbox)
    assert before > 0 and (path is None or after < before)


@needs_cli
def test_form_lists_and_fills_fields(cli, tmp_path):
    _make_pdf(tmp_path / "base.pdf", 1)
    steps = [
        {"tool": "doc_open", "args": {"path": "base.pdf"}},
        {"tool": "form_add_field", "args": {"doc": 1, "page": 1, "type": "text",
                                            "name": "Nombre", "rect": [72, 100, 300, 120]}},
        {"tool": "form_add_field", "args": {"doc": 1, "page": 1, "type": "checkbox",
                                            "name": "Acepto", "rect": [72, 140, 90, 158]}},
        {"tool": "doc_save", "args": {"doc": 1, "path": "formulario.pdf"}},
    ]  # fmt: skip
    pdf._run(steps, tmp_path)
    form = tmp_path / "formulario.pdf"
    listing = pdf.form(form, None, tmp_path / "outbox")
    assert isinstance(listing, str) and "Nombre · text" in listing and "Acepto" in listing
    filled = pdf.form(form, {"Nombre": "Ana Pérez", "Acepto": True}, tmp_path / "outbox")
    assert isinstance(filled, Path)
    assert "Nombre · text · Ana Pérez" in str(pdf.form(filled, None, tmp_path / "outbox"))
