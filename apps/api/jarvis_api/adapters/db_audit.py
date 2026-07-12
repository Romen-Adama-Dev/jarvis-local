from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import AuditLog
from packages.security.audit import AuditEvent, AuditSink


class DbAuditSink(AuditSink):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEvent) -> None:
        self._session.add(
            AuditLog(
                actor=event.actor,
                action=event.action,
                resource=event.resource,
                outcome=event.outcome,
                correlation_id=event.correlation_id,
                details=event.details,
            )
        )
        await self._session.commit()
