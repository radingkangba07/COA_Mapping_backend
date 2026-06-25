import logging
from typing import Any
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from fastapi.responses import JSONResponse

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.projects.dependencies import get_project_service, require_project_access
from src.modules.projects.schemas import (
    AccessGrant,
    AccessResponse,
    AccessUpdate,
    ProjectCreate,
    ProjectCreateFull,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from src.modules.projects.service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["projects"])


# --- Projects ---


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreateFull,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    try:
        return await service.create_project_full(data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create project '%s'", data.name)
        return JSONResponse(status_code=500, content={"detail": "Failed to create project"})


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    org_id: UUID | None = Query(None),
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    try:
        projects = await service.list_projects(user, skip=skip, limit=limit, org_id=org_id)
        return ProjectListResponse(
            projects=[ProjectResponse(**p) for p in projects],
            total=len(projects),
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list projects")
        return JSONResponse(status_code=500, content={"detail": "Failed to list projects"})


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    _access=Depends(require_project_access("viewer")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        return await service.get_project_with_users(project_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get project"})


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        return await service.update_project(project_id, data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update project"})


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    _access=Depends(require_project_access("admin")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.delete_project(project_id)
        return {"status": "deleted"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to delete project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to delete project"})


# --- Access Control ---


@router.post("/projects/{project_id}/access")
async def grant_access(
    project_id: UUID,
    data: AccessGrant,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("approver")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.grant_access(project_id, data.email, data.permission, user, background_tasks)
        return {"success": True, "message": f"Access granted to {data.email}"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to grant access on project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to grant access"})


@router.patch("/projects/{project_id}/access/{user_id}")
async def update_access(
    project_id: UUID,
    user_id: UUID,
    data: AccessUpdate,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("approver")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.update_access(project_id, user_id, data.permission, user)
        return {"success": True, "message": f"Access updated to {data.permission}"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update access on project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update access"})


@router.delete("/projects/{project_id}/access/{user_id}")
async def revoke_access(
    project_id: UUID,
    user_id: UUID,
    _access=Depends(require_project_access("approver")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.revoke_access(project_id, user_id)
        return {"success": True, "message": f"Access revoked from {user_id}"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to revoke access on project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to revoke access"})


@router.get("/projects/{project_id}/access", response_model=list[AccessResponse])
async def list_access(
    project_id: UUID,
    _access=Depends(require_project_access("viewer")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        rows = await service.get_access_list(project_id)
        return [AccessResponse(**row) for row in rows]
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list access for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list access"})


# --- Dashboard ---


@router.get("/dashboard/projects/{project_id}")
async def dashboard_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        return await service.get_project_detail(project_id, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to load project detail %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load project detail"})


# --- Dashboard CRUD aliases (legacy frontend uses /dashboard/projects/* for writes) ---


@router.post(
    "/dashboard/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False
)
async def dashboard_create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    try:
        return await service.create_project(data, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to create project via dashboard")
        return JSONResponse(status_code=500, content={"detail": "Failed to create project"})


@router.patch("/dashboard/projects/{project_id}", include_in_schema=False)
async def dashboard_update_project(
    project_id: UUID,
    data: dict[str, Any],
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        update = ProjectUpdate(**{k: v for k, v in data.items() if k in ProjectUpdate.model_fields})
        return await service.update_project(project_id, update, user)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update project %s via dashboard", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update project"})


@router.post("/dashboard/projects/{project_id}/mappings", include_in_schema=False)
async def dashboard_save_mappings(
    project_id: UUID,
    mappings: list[dict[str, Any]],
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        from src.modules.mappings.dependencies import get_mapping_service
        from src.modules.mappings.schemas import MappingUpsert

        mapping_service = get_mapping_service()
        mapping_upserts = [MappingUpsert(**m) for m in mappings]
        return await mapping_service.bulk_save(project_id, mapping_upserts)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to save mappings for project %s via dashboard", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to save mappings"})


@router.post("/dashboard/projects/{project_id}/access", include_in_schema=False)
async def dashboard_grant_access(
    project_id: UUID,
    data: AccessGrant,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("approver")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.grant_access(project_id, data.email, data.permission, user)
        return {"success": True, "message": f"Access granted to {data.email}"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to grant access on project %s via dashboard", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to grant access"})


@router.delete("/dashboard/projects/{project_id}/access/{target_user_id}", include_in_schema=False)
async def dashboard_revoke_access(
    project_id: UUID,
    target_user_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("approver")),
    service: ProjectService = Depends(get_project_service),
):
    try:
        await service.revoke_access(project_id, target_user_id)
        return {"success": True, "message": f"Access revoked from {target_user_id}"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to revoke access on project %s via dashboard", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to revoke access"})
