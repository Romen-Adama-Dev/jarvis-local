import asyncio

import pytest

from packages.core.errors import NotFoundError, ValidationFailedError
from packages.security.confirmation import ConfirmationService, PendingConfirmation


class _MemoryStore:
    def __init__(self) -> None:
        self.items: dict[str, PendingConfirmation] = {}

    async def save(self, confirmation: PendingConfirmation) -> None:
        self.items[confirmation.token] = confirmation

    async def get(self, token: str) -> PendingConfirmation | None:
        return self.items.get(token)

    async def delete(self, token: str) -> None:
        self.items.pop(token, None)

    async def pop(self, token: str) -> PendingConfirmation | None:
        return self.items.pop(token, None)


async def test_concurrent_confirms_only_one_wins():
    service = ConfirmationService(_MemoryStore(), ttl_seconds=60)
    pending = await service.request(1, "email.send", "Enviar")
    results = await asyncio.gather(
        service.confirm(1, pending.token),
        service.confirm(1, pending.token),
        return_exceptions=True,
    )
    assert sum(isinstance(r, PendingConfirmation) for r in results) == 1
    assert sum(isinstance(r, NotFoundError) for r in results) == 1


async def test_other_user_cannot_consume_confirmation():
    service = ConfirmationService(_MemoryStore(), ttl_seconds=60)
    pending = await service.request(1, "email.send", "Enviar")
    with pytest.raises(ValidationFailedError):
        await service.confirm(2, pending.token)
    assert (await service.confirm(1, pending.token)).token == pending.token


async def test_expired_confirmation_is_consumed():
    store = _MemoryStore()
    service = ConfirmationService(store, ttl_seconds=-1)
    pending = await service.request(1, "email.send", "Enviar")
    with pytest.raises(ValidationFailedError, match="caducado"):
        await service.confirm(1, pending.token)
    assert pending.token not in store.items
