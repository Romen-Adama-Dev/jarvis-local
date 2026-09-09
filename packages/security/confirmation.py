import secrets
import time
from dataclasses import dataclass, field
from typing import Protocol

from packages.core.errors import NotFoundError, ValidationFailedError


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    token: str
    telegram_user_id: int
    action: str
    summary: str
    created_at: float
    expires_at: float
    payload: dict = field(default_factory=dict)


class ConfirmationStore(Protocol):
    async def save(self, confirmation: PendingConfirmation) -> None: ...

    async def get(self, token: str) -> PendingConfirmation | None: ...

    async def delete(self, token: str) -> None: ...


class ConfirmationService:
    def __init__(self, store: ConfirmationStore, ttl_seconds: int) -> None:
        self._store = store
        self._ttl_seconds = ttl_seconds

    async def request(
        self,
        telegram_user_id: int,
        action: str,
        summary: str,
        payload: dict | None = None,
    ) -> PendingConfirmation:
        now = time.time()
        confirmation = PendingConfirmation(
            token=secrets.token_urlsafe(16),
            telegram_user_id=telegram_user_id,
            action=action,
            summary=summary,
            created_at=now,
            expires_at=now + self._ttl_seconds,
            payload=payload or {},
        )
        await self._store.save(confirmation)
        return confirmation

    async def confirm(self, telegram_user_id: int, token: str) -> PendingConfirmation:
        pending = await self._store.get(token)
        if pending is None:
            raise NotFoundError("Confirmación no encontrada o ya usada")
        if pending.telegram_user_id != telegram_user_id:
            raise ValidationFailedError("La confirmación no pertenece a este usuario")
        if time.time() > pending.expires_at:
            await self._store.delete(token)
            raise ValidationFailedError("La confirmación ha caducado, repite la orden")
        await self._store.delete(token)
        return pending
