"""Autenticación OAuth2 (device code flow) contra Microsoft Graph.

Base compartida para las capacidades de correo (`feature/mcp-email`) y
calendario (`feature/mcp-calendar`), que aún no existen en esta rama. Aquí
solo vive lo necesario para obtener y refrescar un token de acceso de Graph
para el usuario dueño del tenant; ninguna llamada a Graph propiamente dicha
(ver `packages/msgraph/client.py`).

El login interactivo (flujo de código de dispositivo) solo debe ejecutarse
desde `scripts/configure-msgraph`, en el momento de la puesta en marcha:
la API y el worker nunca deben bloquear una petición esperando que el
propietario complete un login en el navegador. Por eso
`MsGraphAuthenticator.get_token()` es puramente "silencioso" (usa la caché de
MSAL o falla con `ProviderUnavailableError`), y `interactive_device_code_login`
—la única función que sí inicia el flujo interactivo— vive en este módulo
para que el script de configuración la reutilice, pero nunca se llama desde
`apps/api` ni `apps/worker`.
"""

from pathlib import Path

import msal

from packages.core.errors import ProviderUnavailableError
from packages.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TOKEN_CACHE_PATH = Path.home() / ".openclaw" / "secrets" / "msgraph_token_cache.json"

_LOGIN_HINT = (
    "No hay una sesión válida de Microsoft Graph (caché de token ausente, "
    "vacía o caducada sin refresh token utilizable). Ejecuta "
    "'scripts/configure-msgraph' para iniciar sesión (flujo de código de "
    "dispositivo) y vuelve a intentarlo."
)


class MsGraphTokenStore:
    """Persiste la caché de tokens de MSAL en un fichero JSON fuera del repo.

    Nunca se registra (log) el contenido de la caché: incluye refresh tokens.
    El fichero se escribe con permisos 600 y el directorio padre, si no
    existe, se crea con 700.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_TOKEN_CACHE_PATH

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if self._path.exists():
            cache.deserialize(self._path.read_text(encoding="utf-8"))
        return cache

    def save(self, cache: msal.SerializableTokenCache) -> None:
        if not cache.has_state_changed:
            return
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._path.write_text(cache.serialize(), encoding="utf-8")
        self._path.chmod(0o600)


class MsGraphAuthenticator:
    """Obtiene tokens de acceso de Microsoft Graph a partir de la caché MSAL.

    Nunca inicia un flujo interactivo: si no hay una cuenta en caché o el
    refresco silencioso falla, `get_token()` lanza `ProviderUnavailableError`
    con instrucciones para ejecutar `scripts/configure-msgraph`.
    """

    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        scopes: list[str],
        *,
        token_store: MsGraphTokenStore | None = None,
    ) -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = scopes
        self._token_store = token_store or MsGraphTokenStore()

    def _authority(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant_id}"

    def _build_app(self, cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
        return msal.PublicClientApplication(
            self._client_id, authority=self._authority(), token_cache=cache
        )

    def get_token(self) -> str:
        cache = self._token_store.load()
        app = self._build_app(cache)
        accounts = app.get_accounts()

        result = None
        if accounts:
            result = app.acquire_token_silent(self._scopes, account=accounts[0])

        self._token_store.save(cache)

        if not result or "access_token" not in result:
            logger.warning("msgraph_no_cached_token", tenant_id=self._tenant_id)
            raise ProviderUnavailableError(_LOGIN_HINT)

        return result["access_token"]


def interactive_device_code_login(
    client_id: str,
    tenant_id: str,
    scopes: list[str],
    *,
    token_store: MsGraphTokenStore | None = None,
) -> None:
    """Ejecuta un login interactivo por código de dispositivo y persiste el resultado.

    Pensado para ser invocado ÚNICAMENTE por `scripts/configure-msgraph`, a
    petición explícita del propietario. Imprime la URL y el código que hay
    que introducir en https://microsoft.com/devicelogin y bloquea hasta que
    el usuario completa el login (o expira el código).
    """
    store = token_store or MsGraphTokenStore()
    cache = store.load()
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        store.save(cache)
        raise ProviderUnavailableError(
            "No se pudo iniciar el flujo de código de dispositivo: "
            f"{flow.get('error_description', flow)}"
        )

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    store.save(cache)

    if not result or "access_token" not in result:
        error = (result or {}).get("error_description", result)
        raise ProviderUnavailableError(f"Login de Microsoft Graph fallido: {error}")

    logger.info("msgraph_login_ok", tenant_id=tenant_id, cache_path=str(store.path))
