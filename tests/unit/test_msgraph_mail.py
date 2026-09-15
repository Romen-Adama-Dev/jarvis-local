import json

import httpx
import pytest

from packages.core.attachments import Attachment
from packages.msgraph.client import MsGraphClient
from packages.msgraph.mail import get_message, list_inbox, send_mail


def _client(handler) -> MsGraphClient:
    transport = httpx.MockTransport(handler)
    return MsGraphClient(lambda: "fake-token", transport=transport)


@pytest.mark.asyncio
async def test_list_inbox_requests_inbox_with_expected_params():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/mailFolders/inbox/messages"
        assert request.url.params["$top"] == "5"
        assert request.url.params["$select"] == "id,subject,from,receivedDateTime,bodyPreview"
        assert request.url.params["$orderby"] == "receivedDateTime desc"
        return httpx.Response(200, json={"value": [{"id": "1", "subject": "hola"}]})

    client = _client(handler)
    result = await list_inbox(client, top=5)

    assert result == [{"id": "1", "subject": "hola"}]
    await client.aclose()


@pytest.mark.asyncio
async def test_list_inbox_default_top():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["$top"] == "10"
        return httpx.Response(200, json={"value": []})

    client = _client(handler)
    result = await list_inbox(client)

    assert result == []
    await client.aclose()


@pytest.mark.asyncio
async def test_get_message_requests_expected_select():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/messages/abc123"
        assert (
            request.url.params["$select"]
            == "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body"
        )
        return httpx.Response(200, json={"id": "abc123", "subject": "hola"})

    client = _client(handler)
    result = await get_message(client, "abc123")

    assert result == {"id": "abc123", "subject": "hola"}
    await client.aclose()


@pytest.mark.asyncio
async def test_send_mail_posts_expected_graph_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1.0/me/sendMail"
        body = json.loads(request.content)
        assert body == {
            "message": {
                "subject": "Asunto",
                "body": {"contentType": "Text", "content": "Cuerpo"},
                "toRecipients": [{"emailAddress": {"address": "a@example.com"}}],
                "ccRecipients": [{"emailAddress": {"address": "b@example.com"}}],
            }
        }
        return httpx.Response(202)

    client = _client(handler)
    await send_mail(
        client,
        to=["a@example.com"],
        subject="Asunto",
        body="Cuerpo",
        cc=["b@example.com"],
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_send_mail_omits_cc_when_not_provided():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "ccRecipients" not in body["message"]
        return httpx.Response(202)

    client = _client(handler)
    await send_mail(client, to=["a@example.com"], subject="Asunto", body="Cuerpo")
    await client.aclose()


@pytest.mark.asyncio
async def test_send_mail_includes_file_attachments_as_base64():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["message"]["attachments"] == [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": "resumen.pdf",
                "contentType": "application/pdf",
                "contentBytes": "JVBERi0xLjc=",
            }
        ]
        return httpx.Response(202)

    client = _client(handler)
    await send_mail(
        client,
        to=["a@example.com"],
        subject="Asunto",
        body="Cuerpo",
        attachments=[Attachment("resumen.pdf", b"%PDF-1.7", "application/pdf")],
    )
    await client.aclose()
