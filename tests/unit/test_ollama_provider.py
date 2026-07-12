import json

import httpx
import pytest

from packages.inference.base import ChatMessage, Role
from packages.inference.ollama import OllamaProvider


def _provider(handler) -> OllamaProvider:
    transport = httpx.MockTransport(handler)
    return OllamaProvider(
        "http://127.0.0.1:11434", "qwen2.5:7b-instruct-q4_K_M", transport=transport
    )


@pytest.mark.asyncio
async def test_chat_parses_message_and_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:7b-instruct-q4_K_M"
        assert body["messages"] == [{"role": "user", "content": "hola"}]
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hola de vuelta"},
                "done": True,
                "prompt_eval_count": 5,
                "eval_count": 3,
            },
        )

    provider = _provider(handler)
    result = await provider.chat([ChatMessage(role=Role.USER, content="hola")])

    assert result.text == "hola de vuelta"
    assert result.provider == "ollama"
    assert result.model == "qwen2.5:7b-instruct-q4_K_M"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 3
    assert result.finish_reason == "stop"
    await provider.aclose()


@pytest.mark.asyncio
async def test_chat_uses_model_override():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body["model"]
        return httpx.Response(
            200,
            json={
                "message": {"content": "ok"},
                "done": True,
                "eval_count": 1,
                "prompt_eval_count": 1,
            },
        )

    provider = _provider(handler)
    await provider.chat(
        [ChatMessage(role=Role.USER, content="hola")], model="mistral:7b-instruct-q4_K_M"
    )

    assert seen["model"] == "mistral:7b-instruct-q4_K_M"
    await provider.aclose()


@pytest.mark.asyncio
async def test_health_reports_unhealthy_on_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = _provider(handler)
    health = await provider.health()

    assert health.healthy is False
    assert health.provider == "ollama"
    await provider.aclose()


@pytest.mark.asyncio
async def test_health_reports_healthy_with_version():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/version"
        return httpx.Response(200, json={"version": "0.31.2"})

    provider = _provider(handler)
    health = await provider.health()

    assert health.healthy is True
    assert health.detail == "0.31.2"
    await provider.aclose()


@pytest.mark.asyncio
async def test_list_models_maps_tool_support():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen2.5:7b-instruct-q4_K_M",
                        "size": 4700000000,
                        "details": {"family": "qwen2", "families": ["qwen2"]},
                    },
                    {
                        "name": "nomic-embed-text",
                        "size": 274000000,
                        "details": {"family": "nomic-bert", "families": ["nomic-bert"]},
                    },
                ]
            },
        )

    provider = _provider(handler)
    models = await provider.list_models()

    assert models[0].name == "qwen2.5:7b-instruct-q4_K_M"
    assert models[0].supports_tools is True
    assert models[1].supports_tools is False
    await provider.aclose()


def test_count_tokens_is_deterministic():
    provider = OllamaProvider("http://127.0.0.1:11434", "qwen2.5:7b-instruct-q4_K_M")
    assert provider.count_tokens("hola mundo") > 0
    assert provider.count_tokens("") == 0


def test_capabilities_declare_tool_support():
    provider = OllamaProvider("http://127.0.0.1:11434", "qwen2.5:7b-instruct-q4_K_M")
    caps = provider.capabilities()
    assert caps.provider == "ollama"
    assert caps.supports_tools is True
    assert caps.supports_chat is True
