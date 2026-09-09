import json

import httpx
import pytest

from packages.core.errors import ProviderUnavailableError
from packages.msgraph.client import MsGraphClient


def _client(handler) -> MsGraphClient:
    transport = httpx.MockTransport(handler)
    return MsGraphClient(lambda: "fake-token", transport=transport)


@pytest.mark.asyncio
async def test_get_attaches_bearer_token_and_returns_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/messages"
        assert request.headers["Authorization"] == "Bearer fake-token"
        return httpx.Response(200, json={"value": []})

    client = _client(handler)
    result = await client.get("/me/messages")

    assert result == {"value": []}
    await client.aclose()


@pytest.mark.asyncio
async def test_post_sends_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body == {"subject": "hola"}
        return httpx.Response(201, json={"id": "abc123"})

    client = _client(handler)
    result = await client.post("/me/events", json={"subject": "hola"})

    assert result == {"id": "abc123"}
    await client.aclose()


@pytest.mark.asyncio
async def test_non_2xx_response_raises_provider_unavailable_with_truncated_body():
    long_error = "x" * 2000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=long_error)

    client = _client(handler)
    with pytest.raises(ProviderUnavailableError) as excinfo:
        await client.get("/me/messages")

    assert "400" in str(excinfo.value)
    assert len(excinfo.value.message) < 1200
    await client.aclose()


@pytest.mark.asyncio
async def test_connection_error_raises_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(handler)
    with pytest.raises(ProviderUnavailableError):
        await client.get("/me/messages")
    await client.aclose()


@pytest.mark.asyncio
async def test_delete_handles_empty_204_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(204)

    client = _client(handler)
    result = await client.delete("/me/events/abc123")

    assert result == {}
    await client.aclose()
