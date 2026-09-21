import httpx

from apps.worker.jarvis_worker.tasks import _is_generation_timeout


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://127.0.0.1:11500/v1/chat/completions")
    return httpx.HTTPStatusError(
        "", request=request, response=httpx.Response(code, request=request)
    )


def test_timeouts_are_not_retried() -> None:
    assert _is_generation_timeout(_status_error(504))
    assert _is_generation_timeout(httpx.ReadTimeout("sin respuesta"))


def test_other_errors_are_retried() -> None:
    assert not _is_generation_timeout(_status_error(500))
    assert not _is_generation_timeout(_status_error(503))
    assert not _is_generation_timeout(RuntimeError("CUDA out of memory"))
