import pytest

from packages.core.errors import ValidationFailedError
from packages.security.confirmation import ConfirmationService, PendingConfirmation
from packages.security.telegram_approval import (
    approval_keyboard,
    email_approval_text,
    send_approval,
)

TOKEN = "AbCdEf0123456789_-xYzW"


def test_keyboard_callbacks_fit_telegram_and_carry_token():
    buttons = approval_keyboard(TOKEN)["inline_keyboard"][0]
    assert [b["callback_data"] for b in buttons] == [
        f"correo:enviar:{TOKEN}",
        f"correo:descartar:{TOKEN}",
    ]
    assert all(len(b["callback_data"].encode()) <= 64 for b in buttons)


def test_approval_text_shows_everything_that_will_be_sent():
    draft = {"to": ["a@b.c"], "cc": ["d@e.f"], "subject": "Hola", "body": "Cuerpo real"}
    text = email_approval_text(draft, "informe.pdf", 10)
    for part in ("Para: a@b.c", "CC: d@e.f", "Asunto: Hola", "Adjunto: informe.pdf", "Cuerpo real"):
        assert part in text
    assert text.endswith("Caduca en 10 min.")


def test_long_body_is_trimmed_to_fit_a_telegram_message():
    draft = {"to": ["a@b.c"], "subject": "x", "body": "a" * 10_000}
    text = email_approval_text(draft, None, 10)
    assert len(text) < 4096
    assert "recortado" in text


@pytest.mark.asyncio
async def test_without_bot_token_nothing_can_be_approved():
    with pytest.raises(ValidationFailedError):
        await send_approval("", 1, "texto", TOKEN)
    with pytest.raises(ValidationFailedError):
        await send_approval("change-me", 1, "texto", TOKEN)


class _Store:
    def __init__(self):
        self.items: dict[str, PendingConfirmation] = {}

    async def save(self, confirmation: PendingConfirmation) -> None:
        self.items[confirmation.token] = confirmation

    async def get(self, token: str) -> PendingConfirmation | None:
        return self.items.get(token)

    async def delete(self, token: str) -> None:
        self.items.pop(token, None)

    async def pop(self, token: str) -> PendingConfirmation | None:
        return self.items.pop(token, None)


@pytest.mark.asyncio
async def test_cancel_removes_the_pending_draft():
    store = _Store()
    service = ConfirmationService(store, 600)
    pending = await service.request(1, "send_email", "x")
    await service.cancel(pending.token)
    assert store.items == {}
