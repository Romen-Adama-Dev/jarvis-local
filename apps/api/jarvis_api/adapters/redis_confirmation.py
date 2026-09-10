import json
import time

import redis.asyncio as redis_asyncio

from packages.security.confirmation import ConfirmationStore, PendingConfirmation

_KEY_PREFIX = "jarvis:confirmation:"


class RedisConfirmationStore(ConfirmationStore):
    def __init__(self, client: redis_asyncio.Redis) -> None:
        self._client = client

    async def save(self, confirmation: PendingConfirmation) -> None:
        ttl = max(int(confirmation.expires_at - time.time()), 1)
        serialized = json.dumps(
            {
                "token": confirmation.token,
                "telegram_user_id": confirmation.telegram_user_id,
                "action": confirmation.action,
                "summary": confirmation.summary,
                "created_at": confirmation.created_at,
                "expires_at": confirmation.expires_at,
                "payload": confirmation.payload,
            }
        )
        await self._client.set(_KEY_PREFIX + confirmation.token, serialized, ex=ttl)

    async def get(self, token: str) -> PendingConfirmation | None:
        raw = await self._client.get(_KEY_PREFIX + token)
        if raw is None:
            return None
        data = json.loads(raw)
        data.setdefault("payload", {})
        return PendingConfirmation(**data)

    async def delete(self, token: str) -> None:
        await self._client.delete(_KEY_PREFIX + token)
