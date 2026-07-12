from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class InferenceResult:
    text: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelInfo:
    name: str
    provider: str
    size_bytes: int | None = None
    supports_tools: bool = False


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    healthy: bool
    provider: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    supports_chat: bool
    supports_tools: bool
    supports_streaming: bool
    max_context_tokens: int
    typical_latency_class: str  # "fast" | "slow"


class InferenceProvider(Protocol):
    name: str

    async def generate(
        self, prompt: str, *, model: str | None = None, **kwargs: object
    ) -> InferenceResult: ...

    async def chat(
        self, messages: list[ChatMessage], *, model: str | None = None, **kwargs: object
    ) -> InferenceResult: ...

    async def health(self) -> ProviderHealth: ...

    async def list_models(self) -> list[ModelInfo]: ...

    def count_tokens(self, text: str) -> int: ...

    def capabilities(self) -> ProviderCapabilities: ...
