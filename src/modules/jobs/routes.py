import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.modules.jobs.dependencies import get_job_service
from src.modules.jobs.schemas import JobCreate, JobResponse, JobResultResponse, JobStatusResponse
from src.modules.jobs.service import JobService
from src.modules.projects.dependencies import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    data: JobCreate,
    user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.create_job(data.project_id, data.job_type, data.input_data)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create job for project %s", data.project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to create job"})


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.get_job(job_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get job %s", job_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get job"})


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.get_status(job_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get job status %s", job_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get job status"})


@router.get("/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(
    job_id: UUID,
    user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.get_result(job_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get job result %s", job_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get job result"})


@router.get("/project/{project_id}", response_model=list[JobResponse])
async def list_project_jobs(
    project_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    _access=Depends(require_project_access("viewer")),
    service: JobService = Depends(get_job_service),
):
    try:
        return await service.list_project_jobs(project_id, status=status_filter, limit=limit)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list jobs for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list jobs"})


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    user: User = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
):
    try:
        await service.cancel_job(job_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to cancel job %s", job_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to cancel job"})
