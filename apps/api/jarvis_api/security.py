from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.jarvis_api.deps import get_settings_dep
from packages.core.errors import UnauthorizedError
from packages.core.settings import Settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_internal_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    if not settings.jarvis_api_internal_token:
        return
    if credentials is None or credentials.credentials != settings.jarvis_api_internal_token:
        raise UnauthorizedError("Token interno inválido o ausente")
