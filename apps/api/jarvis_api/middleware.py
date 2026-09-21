import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from packages.core.ids import new_correlation_id, set_correlation_id
from packages.core.logging import get_logger

logger = get_logger(__name__)

# Etiquetadas con la plantilla de la ruta (/documents/{document_id}), no con la URL real,
# para que el número de series no crezca con cada documento o conversación.
HTTP_REQUESTS = Counter(
    "jarvis_http_requests_total",
    "Peticiones HTTP atendidas por la API",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "jarvis_http_request_duration_seconds",
    "Duración de las peticiones HTTP de la API",
    ["method", "route"],
    # Las respuestas con el LLM (chat, RAG, actas) tardan decenas de segundos.
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return route.path if isinstance(route, Route) else "sin-ruta"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-correlation-id")
        correlation_id = incoming or new_correlation_id()
        set_correlation_id(correlation_id)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            elapsed = time.perf_counter() - start
            route = _route_template(request)
            if route != "/metrics":
                HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
                HTTP_LATENCY.labels(request.method, route).observe(elapsed)

        response.headers["x-correlation-id"] = correlation_id
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round(elapsed * 1000, 2),
        )
        return response
