import imaplib
from email.message import EmailMessage

import pytest

from packages.core.attachments import Attachment
from packages.core.errors import NotFoundError, ProviderUnavailableError, ValidationFailedError
from packages.imapsmtp.mail import (
    ImapSmtpConfig,
    check_smtp_login,
    get_message,
    list_inbox,
    send_mail,
)

CONFIG = ImapSmtpConfig(
    imap_host="imap.example.com",
    smtp_host="smtp.example.com",
    username="jarvis@example.com",
    password="app-password",
    from_address="jarvis@example.com",
)


def _raw(subject: str, body: str, *, html: bool = False, date: str = "") -> bytes:
    msg = EmailMessage()
    msg["From"] = "Ana Pérez <ana@example.com>"
    msg["To"] = "jarvis@example.com, otra@example.com"
    msg["Cc"] = "copia@example.com"
    msg["Subject"] = subject
    msg["Date"] = date or "Tue, 15 Sep 2026 10:00:00 +0200"
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    return bytes(msg)


class FakeImap:
    def __init__(self, messages: dict[str, bytes], *, login_error: str | None = None) -> None:
        self.messages = messages
        self.login_error = login_error
        self.selected: tuple[str, bool] | None = None
        self.logged_out = False

    def login(self, username: str, password: str):
        if self.login_error:
            raise imaplib.IMAP4.error(self.login_error)
        assert (username, password) == ("jarvis@example.com", "app-password")
        return "OK", [b"logged in"]

    def select(self, mailbox: str, readonly: bool = False):
        self.selected = (mailbox, readonly)
        return "OK", [str(len(self.messages)).encode()]

    def uid(self, command: str, *args: str):
        if command == "SEARCH":
            return "OK", [" ".join(self.messages).encode()]
        assert command == "FETCH"
        uid = args[0]
        raw = self.messages.get(uid)
        if raw is None:
            return "OK", [None]
        return "OK", [(f"1 (UID {uid} BODY[] {{{len(raw)}}}".encode(), raw), b")"]

    def logout(self):
        self.logged_out = True
        return "BYE", [b""]


class FakeSmtp:
    def __init__(self) -> None:
        self.login_args: tuple[str, str] | None = None
        self.sent: list[EmailMessage] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def login(self, username: str, password: str):
        self.login_args = (username, password)

    def send_message(self, msg: EmailMessage):
        self.sent.append(msg)


async def test_list_inbox_returns_newest_first_in_graph_shape_without_marking_read():
    imap = FakeImap(
        {
            "7": _raw("Primero", "hola"),
            "8": _raw("Segundo", "qué tal"),
            "9": _raw("Tercero", "línea uno\n\nlínea dos"),
        }
    )

    result = await list_inbox(CONFIG, top=2, imap_factory=lambda _: imap)

    assert [m["id"] for m in result] == ["9", "8"]
    assert result[0] == {
        "id": "9",
        "subject": "Tercero",
        "from": {"emailAddress": {"name": "Ana Pérez", "address": "ana@example.com"}},
        "receivedDateTime": "2026-09-15T10:00:00+02:00",
        "bodyPreview": "línea uno línea dos",
    }
    assert imap.selected == ('"INBOX"', True)
    assert imap.logged_out


async def test_get_message_extracts_text_from_html_and_recipients():
    imap = FakeImap({"42": _raw("Informe", "<p>Hola <b>Romen</b></p>", html=True)})

    result = await get_message(CONFIG, "42", imap_factory=lambda _: imap)

    assert result["body"]["contentType"] == "Text"
    assert "Hola" in result["body"]["content"]
    assert "<b>" not in result["body"]["content"]
    assert [r["emailAddress"]["address"] for r in result["toRecipients"]] == [
        "jarvis@example.com",
        "otra@example.com",
    ]
    assert result["ccRecipients"][0]["emailAddress"]["address"] == "copia@example.com"


async def test_get_message_rejects_non_numeric_uid():
    with pytest.raises(ValidationFailedError):
        await get_message(CONFIG, "1:* FLAGS", imap_factory=lambda _: FakeImap({}))


async def test_get_message_missing_raises_not_found():
    with pytest.raises(NotFoundError):
        await get_message(CONFIG, "5", imap_factory=lambda _: FakeImap({}))


async def test_login_failure_becomes_provider_unavailable_with_app_password_hint():
    imap = FakeImap({}, login_error="[AUTHENTICATIONFAILED] Invalid credentials")

    with pytest.raises(ProviderUnavailableError, match="contraseña de aplicación"):
        await list_inbox(CONFIG, imap_factory=lambda _: imap)
    assert imap.logged_out


async def test_send_mail_builds_message_with_attachment():
    smtp = FakeSmtp()

    await send_mail(
        CONFIG,
        to=["romen@example.com"],
        subject="Resumen",
        body="Adjunto el resumen.",
        cc=["copia@example.com"],
        attachments=[Attachment("resumen.pdf", b"%PDF-1.7", "application/pdf")],
        smtp_factory=lambda _: smtp,
    )

    assert smtp.login_args == ("jarvis@example.com", "app-password")
    [msg] = smtp.sent
    assert msg["From"] == "jarvis@example.com"
    assert msg["To"] == "romen@example.com"
    assert msg["Cc"] == "copia@example.com"
    assert msg["Subject"] == "Resumen"
    [attachment] = list(msg.iter_attachments())
    assert attachment.get_filename() == "resumen.pdf"
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_content() == b"%PDF-1.7"


async def test_send_mail_rejects_header_injection():
    with pytest.raises(ValidationFailedError):
        await send_mail(
            CONFIG,
            to=["romen@example.com"],
            subject="hola\nBcc: victima@example.com",
            body="x",
            smtp_factory=lambda _: FakeSmtp(),
        )


async def test_check_smtp_login_does_not_send():
    smtp = FakeSmtp()

    await check_smtp_login(CONFIG, smtp_factory=lambda _: smtp)

    assert smtp.login_args == ("jarvis@example.com", "app-password")
    assert smtp.sent == []
