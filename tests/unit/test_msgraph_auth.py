from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.core.errors import ProviderUnavailableError
from packages.msgraph.auth import MsGraphAuthenticator, MsGraphTokenStore


def _store(tmp_path: Path) -> MsGraphTokenStore:
    return MsGraphTokenStore(tmp_path / "msgraph_token_cache.json")


def test_get_token_raises_when_no_accounts_cached(tmp_path: Path):
    fake_app = MagicMock()
    fake_app.get_accounts.return_value = []

    with patch("packages.msgraph.auth.msal.PublicClientApplication", return_value=fake_app):
        authenticator = MsGraphAuthenticator(
            "client-id", "tenant-id", ["Mail.Read"], token_store=_store(tmp_path)
        )
        with pytest.raises(ProviderUnavailableError):
            authenticator.get_token()

    fake_app.acquire_token_silent.assert_not_called()


def test_get_token_raises_when_silent_refresh_fails(tmp_path: Path):
    fake_app = MagicMock()
    fake_app.get_accounts.return_value = [{"username": "user@example.com"}]
    fake_app.acquire_token_silent.return_value = None

    with patch("packages.msgraph.auth.msal.PublicClientApplication", return_value=fake_app):
        authenticator = MsGraphAuthenticator(
            "client-id", "tenant-id", ["Mail.Read"], token_store=_store(tmp_path)
        )
        with pytest.raises(ProviderUnavailableError):
            authenticator.get_token()


def test_get_token_returns_access_token_from_silent_refresh(tmp_path: Path):
    fake_app = MagicMock()
    fake_app.get_accounts.return_value = [{"username": "user@example.com"}]
    fake_app.acquire_token_silent.return_value = {"access_token": "a-valid-token"}

    with patch("packages.msgraph.auth.msal.PublicClientApplication", return_value=fake_app):
        authenticator = MsGraphAuthenticator(
            "client-id", "tenant-id", ["Mail.Read"], token_store=_store(tmp_path)
        )
        token = authenticator.get_token()

    assert token == "a-valid-token"


def test_token_store_writes_cache_with_restrictive_permissions(tmp_path: Path):
    cache_path = tmp_path / "secrets" / "msgraph_token_cache.json"
    store = MsGraphTokenStore(cache_path)

    fake_cache = MagicMock()
    fake_cache.has_state_changed = True
    fake_cache.serialize.return_value = '{"fake": "cache"}'

    store.save(fake_cache)

    assert cache_path.exists()
    assert cache_path.read_text(encoding="utf-8") == '{"fake": "cache"}'
    assert oct(cache_path.stat().st_mode)[-3:] == "600"


def test_token_store_skips_write_when_cache_unchanged(tmp_path: Path):
    cache_path = tmp_path / "msgraph_token_cache.json"
    store = MsGraphTokenStore(cache_path)

    fake_cache = MagicMock()
    fake_cache.has_state_changed = False

    store.save(fake_cache)

    assert not cache_path.exists()
