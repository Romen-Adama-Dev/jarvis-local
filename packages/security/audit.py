import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuditEvent:
    actor: str
    action: str
    resource: str
    outcome: str
    correlation_id: str | None = None
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class AuditSink(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class AuditService:
    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    async def log(
        self,
        *,
        actor: str,
        action: str,
        resource: str,
        outcome: str,
        correlation_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        event = AuditEvent(
            actor=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            correlation_id=correlation_id,
            details=details or {},
        )
        await self._sink.record(event)
