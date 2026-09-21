import json

import httpx

from packages.inference.ollama import OllamaProvider, warm_quietly


async def test_startup_warm_loads_primary_model_resident() -> None:
    calls: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"done": True})

    provider = OllamaProvider("http://ollama", "gemma4:26b", transport=httpx.MockTransport(handler))
    await warm_quietly(provider)
    assert calls == [("/api/generate", {"model": "gemma4:26b", "keep_alive": -1})]


async def test_startup_warm_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama aún no arranca", request=request)

    provider = OllamaProvider("http://ollama", "gemma4:26b", transport=httpx.MockTransport(handler))
    await warm_quietly(provider)
