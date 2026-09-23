from enum import StrEnum

from packages.core.errors import ProviderUnavailableError
from packages.inference.base import ChatMessage, InferenceProvider, InferenceResult, ProviderHealth


class InferenceMode(StrEnum):
    NORMAL = "normal"


class InferenceRouter:
    def __init__(self, providers: dict[InferenceMode, InferenceProvider]) -> None:
        self._providers = providers

    def provider_for(self, mode: InferenceMode) -> InferenceProvider:
        provider = self._providers.get(mode)
        if provider is None:
            raise ProviderUnavailableError(f"No hay proveedor configurado para el modo '{mode}'")
        return provider

    async def chat(
        self,
        mode: InferenceMode,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        **kwargs: object,
    ) -> InferenceResult:
        provider = self.provider_for(mode)
        return await provider.chat(messages, model=model, **kwargs)

    async def generate(
        self, mode: InferenceMode, prompt: str, *, model: str | None = None, **kwargs: object
    ) -> InferenceResult:
        provider = self.provider_for(mode)
        return await provider.generate(prompt, model=model, **kwargs)

    async def health_all(self) -> dict[str, ProviderHealth]:
        result: dict[str, ProviderHealth] = {}
        for mode, provider in self._providers.items():
            result[mode.value] = await provider.health()
        return result
