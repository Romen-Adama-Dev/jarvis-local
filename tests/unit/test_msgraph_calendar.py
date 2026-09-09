import json

import httpx
import pytest

from packages.msgraph.calendar import create_event, get_calendar_view
from packages.msgraph.client import MsGraphClient


def _client(handler) -> MsGraphClient:
    transport = httpx.MockTransport(handler)
    return MsGraphClient(lambda: "fake-token", transport=transport)


@pytest.mark.asyncio
async def test_get_calendar_view_sends_expected_params_and_returns_value():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.0/me/calendarview"
        query = dict(httpx.QueryParams(request.url.query))
        assert query["startDateTime"] == "2026-09-15T00:00:00"
        assert query["endDateTime"] == "2026-09-16T00:00:00"
        assert query["$select"] == "id,subject,start,end,organizer,attendees"
        assert query["$orderby"] == "start/dateTime"
        return httpx.Response(
            200,
            json={"value": [{"id": "1", "subject": "Reunión"}]},
        )

    client = _client(handler)
    events = await get_calendar_view(client, "2026-09-15T00:00:00", "2026-09-16T00:00:00")

    assert events == [{"id": "1", "subject": "Reunión"}]
    await client.aclose()


@pytest.mark.asyncio
async def test_create_event_posts_expected_graph_payload_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1.0/me/events"
        body = json.loads(request.content)
        assert body == {
            "subject": "Sync de proyecto",
            "start": {"dateTime": "2026-09-15T09:00:00", "timeZone": "Europe/Madrid"},
            "end": {"dateTime": "2026-09-15T09:30:00", "timeZone": "Europe/Madrid"},
            "attendees": [
                {"emailAddress": {"address": "a@example.com"}, "type": "required"},
                {"emailAddress": {"address": "b@example.com"}, "type": "required"},
            ],
            "body": {"contentType": "Text", "content": "Agenda: revisar hitos"},
        }
        return httpx.Response(201, json={"id": "evt1", "webLink": "https://outlook.office.com/evt1"})

    client = _client(handler)
    event = await create_event(
        client,
        subject="Sync de proyecto",
        start="2026-09-15T09:00:00",
        end="2026-09-15T09:30:00",
        attendees=["a@example.com", "b@example.com"],
        body="Agenda: revisar hitos",
    )

    assert event == {"id": "evt1", "webLink": "https://outlook.office.com/evt1"}
    await client.aclose()


@pytest.mark.asyncio
async def test_create_event_defaults_no_attendees_and_empty_body():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["attendees"] == []
        assert body["body"] == {"contentType": "Text", "content": ""}
        assert body["start"]["timeZone"] == "Europe/Madrid"
        return httpx.Response(201, json={"id": "evt2"})

    client = _client(handler)
    event = await create_event(
        client,
        subject="Solo yo",
        start="2026-09-15T09:00:00",
        end="2026-09-15T09:30:00",
    )

    assert event == {"id": "evt2"}
    await client.aclose()
