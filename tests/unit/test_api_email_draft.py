import base64

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from apps.api.jarvis_api.deps import (
    get_confirmation_service,
    get_db_session,
    get_mail_backend,
    get_settings_dep,
)
from apps.api.jarvis_api.routers import email
from packages.core.attachments import EMAIL_ATTACHMENT_MAX_BYTES
from packages.core.errors import JarvisError
from packages.security.confirmation import ConfirmationService
from tests.unit.test_api_pm_people import MemoryStore

PDF = b"%PDF-1.4\n% paginas 100-150\n"


def _draft(**extra) -> dict:
    return {
        "to": ["ana@demo.invalid"],
        "subject": "Páginas del PMBOK",
        "body": "Te lo adjunto.",
        "telegram_user_id": 42,
        **extra,
    }


def _file(name: str = "pmbok-7ed-paginas-1010.pdf", content: bytes = PDF) -> dict:
    return {"filename": name, "content_base64": base64.b64encode(content).decode()}


class FakeBackend:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_mail(self, **kwargs) -> None:
        self.sent.append(kwargs)


@pytest.fixture
def client(monkeypatch, tmp_path):
    store, approvals, backend = MemoryStore(), [], FakeBackend()

    class Settings:
        telegram_bot_token = "bot"
        confirmation_ttl_seconds = 600
        jarvis_data_dir = tmp_path

    async def fake_send(bot, chat, text, token):
        approvals.append({"chat": chat, "text": text, "token": token})

    async def no_db():
        yield None

    monkeypatch.setattr(email, "send_approval", fake_send)
    app = FastAPI()
    app.include_router(email.router)

    @app.exception_handler(JarvisError)
    async def jarvis_error(request: Request, exc: JarvisError) -> JSONResponse:
        # Como en apps/api/jarvis_api/main.py: el mensaje legible con su código HTTP.
        return JSONResponse({"message": exc.message}, status_code=exc.status_code)

    app.dependency_overrides[get_confirmation_service] = lambda: ConfirmationService(store, 600)
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    app.dependency_overrides[get_mail_backend] = lambda: backend
    app.dependency_overrides[get_db_session] = no_db
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.approvals, test_client.backend = approvals, backend  # type: ignore[attr-defined]
    test_client.stored = tmp_path / "email-attachments"  # type: ignore[attr-defined]
    return test_client


def test_file_attachment_is_shown_sent_and_cleaned_up(client):
    response = client.post("/v1/email/draft", json=_draft(attachment_file=_file()))
    assert response.status_code == 202
    assert response.json()["attachment"] == "pmbok-7ed-paginas-1010.pdf (1 KB)"
    [approval] = client.approvals
    assert "Adjunto: pmbok-7ed-paginas-1010.pdf (1 KB)" in approval["text"]
    assert len(list(client.stored.iterdir())) == 1
    sent = client.post(
        f"/v1/email/draft/{approval['token']}/confirm", json={"telegram_user_id": 42}
    )
    assert sent.json()["sent"] is True
    [mail] = client.backend.sent
    [attachment] = mail["attachments"]
    assert (attachment.filename, attachment.content) == ("pmbok-7ed-paginas-1010.pdf", PDF)
    assert attachment.mime_type == "application/pdf"
    assert list(client.stored.iterdir()) == []


def test_without_attachment_says_so(client):
    response = client.post("/v1/email/draft", json=_draft())
    assert response.status_code == 202 and response.json()["attachment"] is None
    assert "Adjunto:" not in client.approvals[0]["text"]


def test_discarding_removes_the_stored_file(client):
    client.post("/v1/email/draft", json=_draft(attachment_file=_file()))
    token = client.approvals[0]["token"]
    client.post(f"/v1/email/draft/{token}/cancel", json={"telegram_user_id": 42})
    assert list(client.stored.iterdir()) == [] and client.backend.sent == []


def test_rejects_two_attachments_bad_base64_paths_and_huge_files(client, monkeypatch):
    both = client.post(
        "/v1/email/draft", json=_draft(attachment_file=_file(), attachment_job_id="x")
    )
    assert both.status_code == 422 and "Solo un adjunto" in both.json()["message"]
    bad = client.post(
        "/v1/email/draft",
        json=_draft(attachment_file={"filename": "a.pdf", "content_base64": "%%%"}),
    )
    assert bad.status_code == 422
    sneaky = client.post("/v1/email/draft", json=_draft(attachment_file=_file("../../x.pdf")))
    assert sneaky.json()["attachment"] == "x.pdf (1 KB)"
    assert all(p.parent.parent == client.stored for p in client.stored.glob("*/*"))
    monkeypatch.setattr(email, "EMAIL_ATTACHMENT_MAX_BYTES", 10)
    huge = client.post("/v1/email/draft", json=_draft(attachment_file=_file(content=b"x" * 11)))
    assert huge.status_code == 422 and "demasiado grande" in huge.json()["message"]
    assert EMAIL_ATTACHMENT_MAX_BYTES == 18 * 1024 * 1024
