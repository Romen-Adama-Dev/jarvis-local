"""Cliente HTTP genérico y de bajo nivel para Microsoft Graph.

Deliberadamente NO conoce nada de correo ni de calendario: solo sabe hacer
peticiones autenticadas GET/POST/PATCH/DELETE contra `v1.0` de Graph y
traducir respuestas no-2xx a `ProviderUnavailableError`. Los métodos
específicos de cada capacidad (listar mensajes, enviar correo, crear
eventos, consultar disponibilidad...) se añaden en las ramas
`feature/mcp-email` y `feature/mcp-calendar`, construidas sobre esta base -
no forman parte de este módulo.
"""

from collections.abc import Callable
from typing import Any

import httpx

from packages.core.errors import ProviderUnavailableError
from packages.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

TokenGetter = Callable[[], str]


class MsGraphClient:
    """Cliente async mínimo sobre `httpx.AsyncClient` para Microsoft Graph."""

    def __init__(
        self,
        token_getter: TokenGetter,
        *,
        base_url: str = GRAPH_BASE_URL,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token_getter = token_getter
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout_seconds, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._token_getter()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self._client.request(
                method, path, params=params, json=json, headers=headers
            )
        except httpx.HTTPError as exc:
            logger.error("msgraph_request_failed", method=method, path=path, error=str(exc))
            raise ProviderUnavailableError(f"Microsoft Graph no disponible: {exc}") from exc

        if response.status_code // 100 != 2:
            body = response.text[:1000]
            logger.error(
                "msgraph_error_response",
                method=method,
                path=path,
                status=response.status_code,
                body=body,
            )
            raise ProviderUnavailableError(
                f"Microsoft Graph respondió {response.status_code} en {method} {path}: {body}"
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("PATCH", path, json=json)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)
