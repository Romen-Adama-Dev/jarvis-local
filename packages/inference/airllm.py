import time

import httpx
import tiktoken

from packages.core.logging import get_logger
from packages.inference.base import (
    ChatMessage,
    InferenceResult,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    Role,
)

logger = get_logger(__name__)

_TOKENIZER = tiktoken.get_encoding("cl100k_base")


class AirLLMProvider:
    name = "airllm"

    def __init__(
        self,
        service_url: str,
        default_model: str,
        *,
        timeout_seconds: float = 1800.0,
        max_context_tokens: int = 4096,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service_url = service_url.rstrip("/")
        self._default_model = default_model
        self._max_context_tokens = max_context_tokens
        self._client = httpx.AsyncClient(
            base_url=self._service_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self, prompt: str, *, model: str | None = None, **kwargs: object
    ) -> InferenceResult:
        return await self.chat(
            [ChatMessage(role=Role.USER, content=prompt)],
            model=model,
            **kwargs,
        )

    async def chat(
        self, messages: list[ChatMessage], *, model: str | None = None, **kwargs: object
    ) -> InferenceResult:
        target_model = model or self._default_model
        payload: dict[str, object] = {
            "model": target_model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
        }
        for key in ("max_tokens", "temperature"):
            if key in kwargs:
                payload[key] = kwargs[key]

        start = time.perf_counter()
        try:
            response = await self._client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("airllm_chat_failed", model=target_model, error=str(exc))
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        data = response.json()

        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage", {})
        return InferenceResult(
            text=choice.get("message", {}).get("content", ""),
            model=data.get("model", target_model),
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    async def health(self) -> ProviderHealth:
        try:
            response = await self._client.get("/health", timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return ProviderHealth(healthy=False, provider=self.name, detail=str(exc))
        data = response.json()
        status = data.get("status", "unknown")
        detail = f"{status}: {data.get('detail', '')}".rstrip(": ")
        return ProviderHealth(healthy=status == "ready", provider=self.name, detail=detail)

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get("/v1/models", timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        data = response.json()
        return [
            ModelInfo(name=item.get("id", ""), provider=self.name, supports_tools=False)
            for item in data.get("data", [])
        ]

    def count_tokens(self, text: str) -> int:
        return len(_TOKENIZER.encode(text))

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_chat=True,
            supports_tools=False,
            supports_streaming=False,
            max_context_tokens=self._max_context_tokens,
            typical_latency_class="slow",
        )
