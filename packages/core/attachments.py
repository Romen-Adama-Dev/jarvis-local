from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Attachment:
    """Archivo adjunto a un correo saliente, independiente del proveedor de correo."""

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"
