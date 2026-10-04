import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.jarvis_api.deps import get_confirmation_service, get_settings_dep
from apps.api.jarvis_api.routers import pm
from packages.security.confirmation import (
    ConfirmationService,
    ConfirmationStore,
    PendingConfirmation,
)

PEOPLE = {
    "people": [{"name": "Diego Sanz", "email": "Diego.Sanz@demo.invalid"}],
    "projects": ["Talleres Norte › App de citas", "Clínica › Web"],
    "telegram_user_id": 42,
}


class MemoryStore(ConfirmationStore):
    def __init__(self) -> None:
        self.items: dict[str, PendingConfirmation] = {}

    async def save(self, confirmation: PendingConfirmation) -> None:
        self.items[confirmation.token] = confirmation

    async def get(self, token: str) -> PendingConfirmation | None:
        return self.items.get(token)

    async def delete(self, token: str) -> None:
        self.items.pop(token, None)

    async def pop(self, token: str) -> PendingConfirmation | None:
        return self.items.pop(token, None)


class Settings:
    telegram_bot_token = "bot"
    confirmation_ttl_seconds = 600


class FakeOP:
    def find_project(self, name):
        return {"name": name}


@pytest.fixture
def client(monkeypatch):
    store, sent, onboarded = MemoryStore(), [], []

    async def fake_send(bot, chat, text, token, namespace):
        sent.append({"chat": chat, "text": text, "token": token, "namespace": namespace})

    monkeypatch.setattr(pm, "send_approval", fake_send)
    monkeypatch.setattr(pm, "_op", FakeOP)
    monkeypatch.setattr(
        pm,
        "onboard",
        lambda op, people, projects: onboarded.append((people, projects)) or ["👤 ok"],
    )
    app = FastAPI()
    app.include_router(pm.router)
    app.dependency_overrides[get_confirmation_service] = lambda: ConfirmationService(store, 600)
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    test_client = TestClient(app, raise_server_exceptions=False)  # errores como en la API: HTTP
    test_client.sent, test_client.onboarded = sent, onboarded  # type: ignore[attr-defined]
    return test_client


def test_draft_sends_buttons_without_returning_the_token(client):
    response = client.post("/v1/pm/people/draft", json=PEOPLE)
    assert response.status_code == 202
    body = response.json()
    assert "token" not in body and "Diego Sanz" in body["summary"]
    [sent] = client.sent
    assert sent["chat"] == 42 and sent["namespace"] == "personas"
    assert "Diego Sanz <diego.sanz@demo.invalid>" in sent["text"]


def test_confirm_onboards_only_for_the_owner(client):
    client.post("/v1/pm/people/draft", json=PEOPLE)
    token = client.sent[0]["token"]
    other = client.post(f"/v1/pm/people/{token}/confirm", json={"telegram_user_id": 7})
    assert other.status_code >= 400 and client.onboarded == []
    done = client.post(f"/v1/pm/people/{token}/confirm", json={"telegram_user_id": 42})
    assert done.json() == {"done": True, "lines": ["👤 ok"]}
    [(people, projects)] = client.onboarded
    assert [p.email for p in people] == ["diego.sanz@demo.invalid"] and len(projects) == 2
    again = client.post(f"/v1/pm/people/{token}/confirm", json={"telegram_user_id": 42})
    assert again.status_code >= 400  # un solo uso


def test_cancel_discards(client):
    client.post("/v1/pm/people/draft", json=PEOPLE)
    token = client.sent[0]["token"]
    assert client.post(f"/v1/pm/people/{token}/cancel", json={"telegram_user_id": 42}).json() == {
        "cancelled": True,
        "people": ["Diego Sanz"],
    }
    assert client.onboarded == []
