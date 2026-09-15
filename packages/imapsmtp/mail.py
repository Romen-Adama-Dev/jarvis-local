"""Correo genérico sobre IMAP (lectura) y SMTP (envío) con la biblioteca estándar.

Alternativa a `packages/msgraph/mail.py` que funciona con cualquier proveedor con
IMAP/SMTP y contraseña de aplicación (Gmail, iCloud, Fastmail, Zoho, un servidor
propio...), sin registrar aplicaciones en Azure ni en Google Cloud. Devuelve los
mensajes con la misma forma que Microsoft Graph (`from.emailAddress.address`,
`receivedDateTime`, `bodyPreview`, `body.content`...) para que el router `/v1/email`
y el servidor MCP `jarvis-email` no dependan del proveedor.

`imaplib`/`smtplib` son síncronos: las funciones públicas son async y delegan en un
hilo. Igual que en `packages/msgraph/mail.py`, aquí no hay confirmación: eso vive en
`apps/api/jarvis_api/routers/email.py`.
"""

import asyncio
import contextlib
import email
import imaplib
import re
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import formatdate, getaddresses, make_msgid, parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

from packages.core.attachments import Attachment
from packages.core.errors import NotFoundError, ProviderUnavailableError, ValidationFailedError
from packages.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_SECONDS = 30
_PREVIEW_CHARS = 255
_UID_RE = re.compile(r"[0-9]+")


@dataclass(frozen=True, slots=True)
class ImapSmtpConfig:
    imap_host: str
    smtp_host: str
    username: str
    password: str
    from_address: str
    imap_port: int = 993
    smtp_port: int = 587
    # "starttls" (puerto 587), "ssl" (puerto 465) o "none" (solo pruebas locales).
    smtp_security: str = "starttls"
    mailbox: str = "INBOX"


# Devuelven un objeto con la interfaz de imaplib.IMAP4 / smtplib.SMTP (inyectable en tests).
ImapFactory = Callable[[ImapSmtpConfig], Any]
SmtpFactory = Callable[[ImapSmtpConfig], Any]


def _connect_imap(config: ImapSmtpConfig) -> imaplib.IMAP4:
    return imaplib.IMAP4_SSL(
        config.imap_host,
        config.imap_port,
        ssl_context=ssl.create_default_context(),
        timeout=_TIMEOUT_SECONDS,
    )


def _connect_smtp(config: ImapSmtpConfig) -> smtplib.SMTP:
    if config.smtp_security == "ssl":
        return smtplib.SMTP_SSL(
            config.smtp_host,
            config.smtp_port,
            timeout=_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    smtp = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=_TIMEOUT_SECONDS)
    try:
        if config.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
    except Exception:
        smtp.close()
        raise
    return smtp


def _describe(exc: Exception) -> str:
    text = str(exc)
    auth_failed = isinstance(exc, smtplib.SMTPAuthenticationError) or (
        isinstance(exc, imaplib.IMAP4.error)
        and any(marker in text.lower() for marker in ("auth", "login", "credential"))
    )
    if auth_failed:
        return (
            "El servidor de correo rechazó el usuario o la contraseña. Usa una contraseña "
            "de aplicación, no la de la cuenta (ver docs/EMAIL.md)."
        )
    return f"Servidor de correo no disponible: {text}"


async def _in_thread(func: Callable[..., Any], *args: Any) -> Any:
    try:
        return await asyncio.to_thread(func, *args)
    except (imaplib.IMAP4.error, smtplib.SMTPException, OSError) as exc:
        logger.error("imapsmtp_request_failed", error=str(exc))
        raise ProviderUnavailableError(_describe(exc)) from exc


def _quote_mailbox(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _logout(imap: Any) -> None:
    # Cerrar la sesión nunca debe tapar el error real.
    with contextlib.suppress(Exception):
        imap.logout()


def _open_mailbox(config: ImapSmtpConfig, imap_factory: ImapFactory) -> Any:
    imap = imap_factory(config)
    try:
        imap.login(config.username, config.password)
        status, _ = imap.select(_quote_mailbox(config.mailbox), readonly=True)
        if status != "OK":
            raise ProviderUnavailableError(f"No existe el buzón IMAP '{config.mailbox}'")
    except Exception:
        _logout(imap)
        raise
    return imap


def _fetch_raw(imap: Any, uid: str) -> bytes | None:
    status, data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
    if status != "OK":
        raise ProviderUnavailableError(f"El servidor IMAP rechazó leer el mensaje {uid}")
    for item in data or []:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _parse(raw: bytes) -> EmailMessage:
    return email.message_from_bytes(raw, policy=default_policy)  # type: ignore[return-value]


def _text_body(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):  # charset desconocido o contenido corrupto
        payload = part.get_payload(decode=True)
        content = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else ""
    if part.get_content_subtype() == "html":
        content = BeautifulSoup(content, "html.parser").get_text("\n")
    return content.strip()


def _address(value: Any) -> dict[str, Any]:
    pairs = getaddresses([str(value)]) if value else []
    name, address = pairs[0] if pairs else ("", "")
    return {"emailAddress": {"name": name, "address": address}}


def _recipients(msg: EmailMessage, header: str) -> list[dict[str, Any]]:
    values = [str(v) for v in msg.get_all(header, [])]
    return [
        {"emailAddress": {"name": name, "address": address}}
        for name, address in getaddresses(values)
        if address
    ]


def _received_at(msg: EmailMessage) -> str:
    try:
        return parsedate_to_datetime(str(msg["Date"])).isoformat()
    except (TypeError, ValueError):
        return ""


def _summary(uid: str, msg: EmailMessage) -> dict[str, Any]:
    return {
        "id": uid,
        "subject": str(msg["Subject"] or ""),
        "from": _address(msg["From"]),
        "receivedDateTime": _received_at(msg),
        "bodyPreview": " ".join(_text_body(msg).split())[:_PREVIEW_CHARS],
    }


def _list_inbox_sync(
    config: ImapSmtpConfig, top: int, imap_factory: ImapFactory
) -> list[dict[str, Any]]:
    imap = _open_mailbox(config, imap_factory)
    try:
        status, data = imap.uid("SEARCH", "ALL")
        if status != "OK":
            raise ProviderUnavailableError("El servidor IMAP rechazó listar el buzón")
        uids = [uid.decode() for uid in data[0].split()] if data and data[0] else []
        messages = []
        for uid in reversed(uids[-top:]):
            raw = _fetch_raw(imap, uid)
            if raw is not None:
                messages.append(_summary(uid, _parse(raw)))
        return messages
    finally:
        _logout(imap)


def _get_message_sync(
    config: ImapSmtpConfig, message_id: str, imap_factory: ImapFactory
) -> dict[str, Any]:
    imap = _open_mailbox(config, imap_factory)
    try:
        raw = _fetch_raw(imap, message_id)
    finally:
        _logout(imap)
    if raw is None:
        raise NotFoundError(f"No existe el correo {message_id}")
    msg = _parse(raw)
    return {
        **_summary(message_id, msg),
        "toRecipients": _recipients(msg, "To"),
        "ccRecipients": _recipients(msg, "Cc"),
        "body": {"contentType": "Text", "content": _text_body(msg)},
    }


def build_message(
    config: ImapSmtpConfig,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    attachments: list[Attachment] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = config.from_address
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    domain = config.from_address.rpartition("@")[2] if "@" in config.from_address else None
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(body)
    for attachment in attachments or []:
        maintype, _, subtype = attachment.mime_type.partition("/")
        msg.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=attachment.filename,
        )
    return msg


def _smtp_session(config: ImapSmtpConfig, smtp_factory: SmtpFactory, msg: EmailMessage | None):
    with smtp_factory(config) as smtp:
        if config.username:
            smtp.login(config.username, config.password)
        if msg is not None:
            smtp.send_message(msg)


async def list_inbox(
    config: ImapSmtpConfig, top: int = 10, *, imap_factory: ImapFactory = _connect_imap
) -> list[dict[str, Any]]:
    """Lista los `top` mensajes más recientes del buzón sin marcarlos como leídos."""
    return await _in_thread(_list_inbox_sync, config, top, imap_factory)


async def get_message(
    config: ImapSmtpConfig, message_id: str, *, imap_factory: ImapFactory = _connect_imap
) -> dict[str, Any]:
    """Obtiene un mensaje completo por su UID IMAP (el `id` que devuelve `list_inbox`)."""
    if not _UID_RE.fullmatch(message_id):
        raise ValidationFailedError(f"Identificador de correo inválido: {message_id}")
    return await _in_thread(_get_message_sync, config, message_id, imap_factory)


async def send_mail(
    config: ImapSmtpConfig,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    attachments: list[Attachment] | None = None,
    *,
    smtp_factory: SmtpFactory = _connect_smtp,
) -> None:
    """Envía un correo por SMTP. No hay confirmación aquí: quien llama ya debe haberla
    obtenido (ver `ConfirmationService`)."""
    try:
        msg = build_message(config, to, subject, body, cc, attachments)
    except ValueError as exc:  # p. ej. saltos de línea en cabeceras
        raise ValidationFailedError(f"Correo inválido: {exc}") from exc
    await _in_thread(_smtp_session, config, smtp_factory, msg)


async def check_smtp_login(
    config: ImapSmtpConfig, *, smtp_factory: SmtpFactory = _connect_smtp
) -> None:
    """Abre y cierra una sesión SMTP autenticada sin enviar nada (scripts/configure-mail)."""
    await _in_thread(_smtp_session, config, smtp_factory, None)
