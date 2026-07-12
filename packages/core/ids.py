import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> None:
    correlation_id_var.set(value)


def get_correlation_id() -> str | None:
    return correlation_id_var.get()
