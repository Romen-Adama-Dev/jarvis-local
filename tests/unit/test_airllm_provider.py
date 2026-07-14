import httpx
import pytest

from packages.inference.airllm import AirLLMProvider
from packages.inference.base import ChatMessage, Role


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_chat_parses_openai_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "airllm-abc",
                "model": "tiny-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hola desde airllm"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            },
        )

    provider = AirLLMProvider("http://airllm.test", "tiny-model", transport=_transport(handler))
    result = await provider.chat([ChatMessage(role=Role.USER, content="hola")])
    assert result.text == "hola desde airllm"
    assert result.provider == "airllm"
    assert result.model == "tiny-model"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 5


async def test_chat_raises_on_service_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "cargando"})

    provider = AirLLMProvider("http://airllm.test", "tiny-model", transport=_transport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await provider.chat([ChatMessage(role=Role.USER, content="hola")])


async def test_health_only_ready_is_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "loading", "detail": "cargando capas"})

    provider = AirLLMProvider("http://airllm.test", "tiny-model", transport=_transport(handler))
    health = await provider.health()
    assert health.healthy is False
    assert "loading" in health.detail


async def test_health_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ready", "detail": ""})

    provider = AirLLMProvider("http://airllm.test", "tiny-model", transport=_transport(handler))
    health = await provider.health()
    assert health.healthy is True


async def test_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"object": "list", "data": [{"id": "tiny-model", "object": "model"}]}
        )

    provider = AirLLMProvider("http://airllm.test", "tiny-model", transport=_transport(handler))
    models = await provider.list_models()
    assert [m.name for m in models] == ["tiny-model"]
    assert models[0].supports_tools is False


def test_capabilities_slow_class():
    provider = AirLLMProvider("http://airllm.test", "tiny-model")
    caps = provider.capabilities()
    assert caps.typical_latency_class == "slow"
    assert caps.supports_streaming is False
