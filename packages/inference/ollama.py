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

# La API /api/tags de Ollama no expone si una familia de modelo soporta el
# campo "tools" del endpoint /api/chat: se determina empíricamente (ver
# docs/BENCHMARKS.md) probando una llamada real con "tools". Este conjunto
# refleja las familias verificadas como compatibles en ese benchmark.
_TOOL_CAPABLE_FAMILIES = {"llama", "qwen2", "gemma4"}


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        host: str,
        default_model: str,
        *,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=self._host, timeout=timeout_seconds, transport=transport
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
            "stream": False,
            # Los modelos con "thinking" (gemma4, qwen3...) razonan por defecto: para responder
            # sobre contexto RAG solo añade latencia. Los modelos sin thinking lo ignoran.
            "think": False,
        }
        options = {k: v for k, v in kwargs.items() if k in {"temperature", "num_ctx", "top_p"}}
        if options:
            payload["options"] = options
        # Salida estructurada: "json" o un esquema JSON que Ollama impone al generar.
        if kwargs.get("format"):
            payload["format"] = kwargs["format"]

        start = time.perf_counter()
        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("ollama_chat_failed", model=target_model, error=str(exc))
            raise
        latency_ms = (time.perf_counter() - start) * 1000
        data = response.json()

        message = data.get("message", {})
        text = message.get("content", "")
        prompt_tokens = int(data.get("prompt_eval_count", 0))
        completion_tokens = int(data.get("eval_count", 0))
        finish_reason = "stop" if data.get("done", True) else "length"

        return InferenceResult(
            text=text,
            model=target_model,
            provider=self.name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw=data,
        )

    async def release_vram(self) -> list[str]:
        response = await self._client.get("/api/ps")
        response.raise_for_status()
        released: list[str] = []
        for item in response.json().get("models", []):
            name = item.get("name")
            if not name:
                continue
            unload = await self._client.post("/api/generate", json={"model": name, "keep_alive": 0})
            unload.raise_for_status()
            released.append(name)
        if released:
            logger.info("ollama_vram_released", models=released)
        return released

    async def warm(self, models: list[str] | None = None) -> None:
        targets = models or [self._default_model]
        ps = await self._client.get("/api/ps")
        ps.raise_for_status()
        loaded = {item.get("name"): item for item in ps.json().get("models", [])}
        for name in targets:
            entry = loaded.get(name)
            degraded = entry is not None and entry.get("size_vram", 0) < entry.get("size", 0)
            if degraded:
                unload = await self._client.post(
                    "/api/generate", json={"model": name, "keep_alive": 0}
                )
                unload.raise_for_status()
            response = await self._client.post(
                "/api/generate", json={"model": name, "keep_alive": -1}
            )
            response.raise_for_status()
        logger.info("ollama_warmed", models=targets)

    async def health(self) -> ProviderHealth:
        try:
            response = await self._client.get("/api/version")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return ProviderHealth(healthy=False, provider=self.name, detail=str(exc))
        return ProviderHealth(
            healthy=True, provider=self.name, detail=response.json().get("version", "")
        )

    async def list_models(self) -> list[ModelInfo]:
        response = await self._client.get("/api/tags")
        response.raise_for_status()
        data = response.json()
        models: list[ModelInfo] = []
        for item in data.get("models", []):
            details = item.get("details", {})
            families = set(details.get("families") or [])
            family = details.get("family")
            supports_tools = (
                bool(families & _TOOL_CAPABLE_FAMILIES) or family in _TOOL_CAPABLE_FAMILIES
            )
            models.append(
                ModelInfo(
                    name=item.get("name", ""),
                    provider=self.name,
                    size_bytes=item.get("size"),
                    supports_tools=supports_tools,
                )
            )
        return models

    def count_tokens(self, text: str) -> int:
        return len(_TOKENIZER.encode(text))

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            supports_chat=True,
            supports_tools=True,
            supports_streaming=True,
            max_context_tokens=8192,
            typical_latency_class="fast",
        )


async def warm_quietly(provider: OllamaProvider) -> None:
    """Precarga el modelo principal sin propagar errores (arranque de la API: si Ollama aún
    no responde, la primera pregunta lo cargará como antes)."""
    try:
        await provider.warm()
    except Exception as exc:
        logger.warning("ollama_warm_failed", error=f"{type(exc).__name__}: {exc}")
