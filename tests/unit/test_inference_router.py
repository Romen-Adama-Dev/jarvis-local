import pytest

from packages.core.errors import ProviderUnavailableError
from packages.inference.base import (
    ChatMessage,
    InferenceResult,
    ModelInfo,
    ProviderCapabilities,
    ProviderHealth,
    Role,
)
from packages.inference.router import InferenceMode, InferenceRouter


class FakeProvider:
    def __init__(self, name: str, *, healthy: bool = True) -> None:
        self.name = name
        self._healthy = healthy
        self.chat_calls: list[list[ChatMessage]] = []

    async def generate(
        self, prompt: str, *, model: str | None = None, **kwargs: object
    ) -> InferenceResult:
        return await self.chat([ChatMessage(role=Role.USER, content=prompt)], model=model)

    async def chat(
        self, messages: list[ChatMessage], *, model: str | None = None, **kwargs: object
    ) -> InferenceResult:
        self.chat_calls.append(messages)
        return InferenceResult(
            text="respuesta",
            model=model or "default",
            provider=self.name,
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1.0,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(healthy=self._healthy, provider=self.name)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model", provider=self.name)]

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_chat=True,
            supports_tools=False,
            supports_streaming=False,
            max_context_tokens=4096,
            typical_latency_class="fast",
        )


@pytest.mark.asyncio
async def test_chat_routes_normal_mode_to_ollama_style_provider():
    ollama = FakeProvider("ollama")
    router = InferenceRouter(providers={InferenceMode.NORMAL: ollama})

    result = await router.chat(InferenceMode.NORMAL, [ChatMessage(role=Role.USER, content="hola")])

    assert result.provider == "ollama"
    assert len(ollama.chat_calls) == 1


@pytest.mark.asyncio
async def test_deep_mode_without_airllm_configured_raises():
    router = InferenceRouter(providers={InferenceMode.NORMAL: FakeProvider("ollama")})

    with pytest.raises(ProviderUnavailableError):
        await router.chat(InferenceMode.DEEP, [ChatMessage(role=Role.USER, content="hola")])


@pytest.mark.asyncio
async def test_health_all_reports_each_provider():
    router = InferenceRouter(
        providers={
            InferenceMode.NORMAL: FakeProvider("ollama", healthy=True),
            InferenceMode.DEEP: FakeProvider("airllm", healthy=False),
        }
    )

    health = await router.health_all()

    assert health["normal"].healthy is True
    assert health["deep"].healthy is False
