from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from apps.api.jarvis_api.middleware import CorrelationIdMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


def test_metrics_use_route_template_not_raw_path() -> None:
    client = TestClient(_app())
    for item_id in (1, 2, 3):
        assert client.get(f"/items/{item_id}").status_code == 200
    assert client.get("/no-existe").status_code == 404

    text = generate_latest().decode()
    assert 'jarvis_http_requests_total{method="GET",route="/items/{item_id}",status="200"}' in text
    assert 'route="sin-ruta",status="404"' in text
    assert "/items/1" not in text
    bucket = 'jarvis_http_request_duration_seconds_bucket{le="0.05",method="GET"'
    assert f'{bucket},route="/items/{{item_id}}"}}' in text


def test_correlation_id_is_echoed() -> None:
    response = TestClient(_app()).get("/items/7", headers={"x-correlation-id": "abc"})
    assert response.headers["x-correlation-id"] == "abc"
