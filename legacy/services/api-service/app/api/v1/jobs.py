"""Job management endpoints for async processing."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.job import Job, JobStatus, JobType
from app.schemas.job import (
    JobCreate,
    JobResponse,
    JobStatusResponse,
    JobResultResponse
)
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])
job_service = JobService()


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    job_data: JobCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new processing job.
    
    This endpoint immediately returns a job_id. The actual processing
    happens asynchronously via the ML service workers.
    
    Poll GET /api/v1/jobs/{job_id}/status to check progress.
    """
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == job_data.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create the job
    job = await job_service.create_job(
        db=db,
        project_id=job_data.project_id,
        job_type=job_data.job_type,
        input_data=job_data.input_data
    )
    
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get full job details."""
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Poll for job status.
    
    This is the primary endpoint for frontend polling.
    Returns a lightweight status response optimized for frequent calls.
    
    Recommended polling interval: 1-2 seconds
    Stop polling when is_complete is True.
    """
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        is_complete=job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value],
        has_error=job.status == JobStatus.FAILED.value,
        result_available=job.result_data is not None
    )


@router.get("/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get job results after completion.
    
    Only call this endpoint after status shows is_complete=True
    and result_available=True.
    """
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
        raise HTTPException(
            status_code=400,
            detail="Job is still processing. Poll /status endpoint first."
        )
    
    return JobResultResponse(
        job_id=job.id,
        status=job.status,
        result_data=job.result_data,
        error_message=job.error_message
    )


@router.get("/project/{project_id}", response_model=List[JobResponse])
async def get_project_jobs(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """Get all jobs for a project."""
    query = select(Job).where(Job.project_id == project_id)
    
    if status:
        query = query.where(Job.status == status)
    
    query = query.order_by(Job.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return [JobResponse.model_validate(j) for j in jobs]


@router.delete("/{job_id}", status_code=204)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending or queued job.
    
    Cannot cancel jobs that are already processing or completed.
    """
    job = await job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.PENDING.value, JobStatus.QUEUED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status}"
        )
    
    await db.delete(job)
    await db.commit()
