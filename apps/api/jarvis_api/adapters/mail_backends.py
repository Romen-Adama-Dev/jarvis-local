"""Backends de correo intercambiables para `/v1/email` (ver docs/EMAIL.md).

`MAIL_PROVIDER=imap` (por defecto) usa `packages/imapsmtp` y funciona con cualquier
proveedor estándar con contraseña de aplicación; `MAIL_PROVIDER=msgraph` usa
`packages/msgraph` (requiere registro de app en Azure, docs/MSGRAPH.md). Los dos
devuelven los mensajes con la forma de Graph.
"""

from collections.abc import Callable
from typing import Any, Protocol

from packages.core.attachments import Attachment
from packages.core.errors import ProviderUnavailableError
from packages.core.settings import Settings
from packages.imapsmtp import mail as imap_mail
from packages.imapsmtp.mail import ImapSmtpConfig
from packages.msgraph import mail as graph_mail
from packages.msgraph.client import MsGraphClient


class MailBackend(Protocol):
    async def list_inbox(self, top: int) -> list[dict[str, Any]]: ...

    async def get_message(self, message_id: str) -> dict[str, Any]: ...

    async def send_mail(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> None: ...


class GraphMailBackend:
    def __init__(self, client: MsGraphClient) -> None:
        self._client = client

    async def list_inbox(self, top: int) -> list[dict[str, Any]]:
        return await graph_mail.list_inbox(self._client, top=top)

    async def get_message(self, message_id: str) -> dict[str, Any]:
        return await graph_mail.get_message(self._client, message_id)

    async def send_mail(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> None:
        await graph_mail.send_mail(
            self._client, to=to, subject=subject, body=body, cc=cc, attachments=attachments
        )


class ImapSmtpMailBackend:
    def __init__(self, config: ImapSmtpConfig) -> None:
        self.config = config

    async def list_inbox(self, top: int) -> list[dict[str, Any]]:
        return await imap_mail.list_inbox(self.config, top=top)

    async def get_message(self, message_id: str) -> dict[str, Any]:
        return await imap_mail.get_message(self.config, message_id)

    async def send_mail(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        attachments: list[Attachment] | None = None,
    ) -> None:
        await imap_mail.send_mail(
            self.config, to=to, subject=subject, body=body, cc=cc, attachments=attachments
        )


def imap_config_from_settings(settings: Settings) -> ImapSmtpConfig:
    required = {
        "IMAP_HOST": settings.imap_host,
        "SMTP_HOST": settings.smtp_host,
        "MAIL_USERNAME": settings.mail_username,
        "MAIL_PASSWORD": settings.mail_password,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ProviderUnavailableError(
            f"Correo sin configurar (faltan {', '.join(missing)}). Ejecuta "
            "scripts/configure-mail (ver docs/EMAIL.md)."
        )
    return ImapSmtpConfig(
        imap_host=settings.imap_host,
        imap_port=settings.imap_port,
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_security=settings.smtp_security,
        username=settings.mail_username,
        password=settings.mail_password,
        from_address=settings.mail_from or settings.mail_username,
        mailbox=settings.imap_mailbox,
    )


def mail_backend_from_settings(
    settings: Settings, graph_client: Callable[[], MsGraphClient]
) -> MailBackend:
    provider = settings.mail_provider.strip().lower()
    if provider == "imap":
        return ImapSmtpMailBackend(imap_config_from_settings(settings))
    if provider == "msgraph":
        return GraphMailBackend(graph_client())
    raise ProviderUnavailableError(
        f"MAIL_PROVIDER desconocido: '{settings.mail_provider}' (valores: imap, msgraph)"
    )
