from typing import cast

import pytest

from apps.api.jarvis_api.adapters.calendar_backends import (
    CalDavCalendarBackend,
    GraphCalendarBackend,
    calendar_backend_from_settings,
)
from apps.api.jarvis_api.adapters.mail_backends import (
    GraphMailBackend,
    ImapSmtpMailBackend,
    mail_backend_from_settings,
)
from packages.core.errors import ProviderUnavailableError
from packages.core.settings import Settings
from packages.msgraph.client import MsGraphClient

MAIL = {
    "imap_host": "imap.example.com",
    "smtp_host": "smtp.example.com",
    "mail_username": "jarvis@example.com",
    "mail_password": "app-password",
}


def _settings(**overrides) -> Settings:
    return Settings(postgres_password="x", _env_file=None, **overrides)  # pyright: ignore[reportCallIssue]


def _no_graph() -> MsGraphClient:
    raise AssertionError("no debe crear el cliente de Graph")


def _graph() -> MsGraphClient:
    """Los backends de Graph solo guardan el cliente al construirse, no lo llaman."""
    return cast(MsGraphClient, object())


def test_imap_backend_uses_username_as_sender_by_default():
    backend = mail_backend_from_settings(_settings(mail_provider="imap", **MAIL), _no_graph)

    assert isinstance(backend, ImapSmtpMailBackend)
    assert backend.config.from_address == "jarvis@example.com"
    assert backend.config.smtp_security == "starttls"


def test_imap_backend_unconfigured_names_missing_variables():
    with pytest.raises(ProviderUnavailableError, match="IMAP_HOST.*MAIL_PASSWORD"):
        mail_backend_from_settings(_settings(mail_provider="imap"), _no_graph)


def test_msgraph_mail_backend_builds_graph_client_lazily():
    backend = mail_backend_from_settings(_settings(mail_provider="msgraph"), _graph)
    assert isinstance(backend, GraphMailBackend)


def test_unknown_mail_provider_is_rejected():
    with pytest.raises(ProviderUnavailableError, match="MAIL_PROVIDER"):
        mail_backend_from_settings(_settings(mail_provider="pop3"), _no_graph)


def test_caldav_backend_reuses_mail_credentials_when_not_set():
    backend = calendar_backend_from_settings(
        _settings(calendar_provider="caldav", caldav_url="https://dav.example.com/", **MAIL),
        _no_graph,
    )

    assert isinstance(backend, CalDavCalendarBackend)
    assert backend.config.username == "jarvis@example.com"
    assert backend.config.password == "app-password"


def test_caldav_backend_unconfigured_is_provider_unavailable():
    with pytest.raises(ProviderUnavailableError, match="CALDAV_URL"):
        calendar_backend_from_settings(_settings(calendar_provider="caldav"), _no_graph)


def test_msgraph_calendar_backend():
    backend = calendar_backend_from_settings(_settings(calendar_provider="msgraph"), _graph)
    assert isinstance(backend, GraphCalendarBackend)
