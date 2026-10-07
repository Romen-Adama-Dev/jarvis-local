from dataclasses import dataclass

# Tamaño máximo de un archivo adjunto a un correo. Gmail admite 25 MB por mensaje y el
# adjunto viaja en base64 (un tercio más), así que 18 MiB deja margen. Microsoft Graph
# limita más (3 MB, ver packages/msgraph/mail.py).
EMAIL_ATTACHMENT_MAX_BYTES = 18 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Attachment:
    """Archivo adjunto a un correo saliente, independiente del proveedor de correo."""

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"
