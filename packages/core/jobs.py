from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import Job


async def mark_running(session: AsyncSession, job: Job) -> None:
    job.status = "running"
    await session.commit()


async def mark_progress(session: AsyncSession, job: Job, percent: int) -> None:
    job.progress = max(0, min(100, percent))
    await session.commit()


async def mark_completed(session: AsyncSession, job: Job, result: dict) -> None:
    job.status = "completed"
    job.progress = 100
    job.result = result
    await session.commit()


async def mark_failed(session: AsyncSession, job: Job, error: str) -> None:
    job.status = "failed"
    job.error = error
    await session.commit()


async def mark_cancelled(session: AsyncSession, job: Job) -> None:
    job.status = "cancelled"
    await session.commit()


async def refresh_is_cancelling(session: AsyncSession, job: Job) -> bool:
    await session.refresh(job)
    return job.status == "cancelling"
