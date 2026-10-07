import pytest

from packages.core.errors import NotFoundError, ValidationFailedError
from packages.core.files import display_name, resolve_local_file, stored_stem

OFFICE = {".pdf", ".xlsx"}


def test_names_without_openclaw_prefix_and_uuid(tmp_path):
    stored = tmp_path / "input-Informe_Q3---0a1b2c.pdf"
    assert stored_stem(stored) == "Informe_Q3"
    assert display_name(stored) == "Informe_Q3.pdf"
    assert display_name(tmp_path / "presupuesto-1012.xlsx") == "presupuesto-1012.xlsx"


def test_resolves_outbox_and_received_files_by_name(tmp_path):
    outbox, inbound = tmp_path / "outbox", tmp_path / "media" / "inbound"
    outbox.mkdir()
    inbound.mkdir(parents=True)
    excel = outbox / "presupuesto-1012.xlsx"
    excel.write_bytes(b"x")
    received = inbound / "input-Acta_reunion---9f.pdf"
    received.write_bytes(b"x")
    roots = [outbox, tmp_path / "media"]
    kwargs = {"suffixes": OFFICE, "max_bytes": 10, "what": "archivo adjuntable"}
    assert resolve_local_file("presupuesto-1012.xlsx", roots, **kwargs) == excel.resolve()
    assert resolve_local_file("Acta reunion.pdf", roots, **kwargs) == received.resolve()
    assert resolve_local_file(str(excel), roots, **kwargs) == excel.resolve()


def test_rejects_other_types_big_files_and_paths_outside(tmp_path):
    (tmp_path / "virus.exe").write_bytes(b"x")
    (tmp_path / "grande.pdf").write_bytes(b"x" * 11)
    kwargs = {"suffixes": OFFICE, "max_bytes": 10, "what": "archivo adjuntable"}
    with pytest.raises(ValidationFailedError, match="no es un archivo adjuntable"):
        resolve_local_file(str(tmp_path / "virus.exe"), [tmp_path], **kwargs)
    with pytest.raises(ValidationFailedError, match="pasa de"):
        resolve_local_file("grande.pdf", [tmp_path], **kwargs)
    with pytest.raises(ValidationFailedError, match="No puedo usar esa ruta"):
        resolve_local_file("/etc/hostname", [tmp_path], **kwargs)
    with pytest.raises(NotFoundError):
        resolve_local_file("otro.pdf", [tmp_path], **kwargs)
