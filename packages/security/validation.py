import zipfile
from pathlib import PurePosixPath

from packages.core.errors import ValidationFailedError

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".csv", ".xlsx"}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_ZIP_UNCOMPRESSED_RATIO = 100
MAX_ZIP_MEMBER_COUNT = 10_000


def validate_filename(filename: str) -> str:
    name = PurePosixPath(filename).name
    if not name or name in (".", ".."):
        raise ValidationFailedError("Nombre de archivo inválido")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValidationFailedError("Nombre de archivo con ruta no permitida (path traversal)")
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationFailedError(f"Extensión no soportada: {suffix}")
    return name


def validate_size(size_bytes: int, max_mb: int) -> None:
    max_bytes = max_mb * 1024 * 1024
    if size_bytes <= 0:
        raise ValidationFailedError("Archivo vacío")
    if size_bytes > max_bytes:
        raise ValidationFailedError(f"Archivo supera el límite de {max_mb}MB")


def validate_mime(detected_mime: str) -> None:
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValidationFailedError(f"Tipo MIME no permitido: {detected_mime}")


def validate_zip_safety(path: str) -> None:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_MEMBER_COUNT:
            raise ValidationFailedError("Archivo comprimido con demasiadas entradas")
        for info in infos:
            if info.file_size == 0:
                continue
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_ZIP_UNCOMPRESSED_RATIO:
                raise ValidationFailedError("Archivo comprimido sospechoso (posible zip bomb)")
            member_name = info.filename
            if member_name.startswith("/") or ".." in PurePosixPath(member_name).parts:
                raise ValidationFailedError("Entrada de archivo comprimido con path traversal")


def resolve_within_root(root: str, relative_path: str) -> str:
    import os

    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root, relative_path))
    if not candidate.startswith(root_real + os.sep) and candidate != root_real:
        raise ValidationFailedError("Ruta fuera del directorio permitido")
    return candidate
