import uuid

from fastapi import APIRouter
from sqlalchemy import select

from apps.api.jarvis_api.deps import DbSession
from apps.api.jarvis_api.schemas import JobListResponse, JobResponse
from packages.core.db.models import Job
from packages.core.errors import ConflictError, NotFoundError

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@router.get("", response_model=JobListResponse)
async def list_jobs(session: DbSession, status: str | None = None) -> JobListResponse:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(200)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return JobListResponse(jobs=[JobResponse.model_validate(r) for r in rows])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, session: DbSession) -> JobResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Trabajo no encontrado")
    return JobResponse.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: uuid.UUID, session: DbSession) -> JobResponse:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Trabajo no encontrado")
    if job.status in TERMINAL_STATUSES:
        raise ConflictError(f"El trabajo ya está en estado terminal: {job.status}")
    job.status = "cancelling"
    await session.commit()
    await session.refresh(job)
    return JobResponse.model_validate(job)
