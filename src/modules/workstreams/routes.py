import logging
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.workstreams.dependencies import (
    get_stage_service,
    get_status_service,
    get_workstream_service,
    require_workstream_project_access,
    resolve_workstream_project_access,
)
from src.modules.workstreams.schemas import (
    StageCompleteResponse,
    StageResponse,
    StatusLogEntry,
    StatusTransitionRequest,
    WorkstreamCreate,
    WorkstreamListResponse,
    WorkstreamResponse,
    WorkstreamUpdate,
)
from src.modules.workstreams.service import StageService, StatusService, WorkstreamService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["workstreams"])


@router.post(
    "/projects/{project_id}/workstreams",
    response_model=WorkstreamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workstream(
    project_id: UUID,
    data: WorkstreamCreate,
    user: User = Depends(get_current_user),
    _access=Depends(require_workstream_project_access("editor")),
    service: WorkstreamService = Depends(get_workstream_service),
):
    try:
        return await service.create(project_id, data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create workstream for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to create workstream"})


@router.get(
    "/projects/{project_id}/workstreams",
    response_model=WorkstreamListResponse,
)
async def list_workstreams(
    project_id: UUID,
    _access=Depends(require_workstream_project_access("viewer")),
    service: WorkstreamService = Depends(get_workstream_service),
):
    try:
        workstreams = await service.list(project_id)
        return WorkstreamListResponse(workstreams=workstreams, total=len(workstreams))
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list workstreams for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list workstreams"})


@router.patch(
    "/projects/{project_id}/workstreams/{workstream_id}",
    response_model=WorkstreamResponse,
)
async def update_workstream(
    project_id: UUID,
    workstream_id: UUID,
    data: WorkstreamUpdate,
    _access=Depends(require_workstream_project_access("editor")),
    service: WorkstreamService = Depends(get_workstream_service),
):
    try:
        return await service.update(workstream_id, data)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update workstream %s", workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update workstream"})


@router.delete(
    "/projects/{project_id}/workstreams/{workstream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workstream(
    project_id: UUID,
    workstream_id: UUID,
    _access=Depends(require_workstream_project_access("editor")),
    service: WorkstreamService = Depends(get_workstream_service),
):
    try:
        await service.delete(workstream_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to delete workstream %s", workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to delete workstream"})


# ── Stage endpoints (DAB-20) ──────────────────────────────────────────────────


@router.get(
    "/workstreams/{workstream_id}/stages",
    response_model=list[StageResponse],
)
async def list_stages(
    workstream_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: StageService = Depends(get_stage_service),
):
    try:
        await resolve_workstream_project_access(workstream_id, user, db, "viewer")
        return await service.list_stages(workstream_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list stages for workstream %s", workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list stages"})


@router.patch(
    "/workstreams/{workstream_id}/stages/{stage_id}/complete",
    response_model=StageCompleteResponse,
)
async def complete_stage(
    workstream_id: UUID,
    stage_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: StageService = Depends(get_stage_service),
):
    try:
        await resolve_workstream_project_access(workstream_id, user, db, "editor")
        return await service.complete_stage(workstream_id, stage_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to complete stage %s on workstream %s", stage_id, workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to complete stage"})


# ── Status endpoints (DAB-21) ─────────────────────────────────────────────────


@router.post(
    "/workstreams/{workstream_id}/status",
    response_model=StatusLogEntry,
    status_code=status.HTTP_201_CREATED,
)
async def transition_status(
    workstream_id: UUID,
    data: StatusTransitionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: StatusService = Depends(get_status_service),
):
    try:
        await resolve_workstream_project_access(workstream_id, user, db, "editor")
        return await service.transition(workstream_id, data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to transition status for workstream %s", workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to transition status"})


@router.get(
    "/workstreams/{workstream_id}/status-log",
    response_model=list[StatusLogEntry],
)
async def list_status_log(
    workstream_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: StatusService = Depends(get_status_service),
):
    try:
        await resolve_workstream_project_access(workstream_id, user, db, "viewer")
        return await service.list_log(workstream_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list status log for workstream %s", workstream_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list status log"})
