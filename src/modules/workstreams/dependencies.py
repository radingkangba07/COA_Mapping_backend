from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError, NotFoundError
from src.modules.auth.dependencies import get_current_user
from src.modules.projects.repository import ProjectAccessRepository
from src.modules.projects.service import permission_level
from src.modules.workstreams.repository import WorkstreamRepository, make_repositories
from src.modules.workstreams.service import StageService, WorkstreamService


def get_stage_service(db: AsyncSession = Depends(get_db)) -> StageService:
    _, workstream_repo, stage_repo = make_repositories(db)
    return StageService(workstream_repo=workstream_repo, stage_repo=stage_repo, session=db)


def get_workstream_service(db: AsyncSession = Depends(get_db)) -> WorkstreamService:
    category_repo, workstream_repo, _ = make_repositories(db)
    return WorkstreamService(
        category_repo=category_repo,
        workstream_repo=workstream_repo,
        session=db,
    )


def require_workstream_project_access(min_permission: str):
    """Resolve the project_id from the URL path and enforce access level.

    Works for routes where project_id is directly in the path.
    """
    async def _check(
        project_id: UUID = Path(...),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        repo = ProjectAccessRepository(db)
        access = await repo.get_user_permission(user.id, project_id)
        if not access or permission_level(access.permission) < permission_level(min_permission):
            raise ForbiddenError("Insufficient permissions")

    return _check


async def resolve_workstream_project_access(
    workstream_id: UUID,
    user: User,
    db: AsyncSession,
    min_permission: str,
) -> None:
    """Resolve the parent project_id from a workstream row and enforce access.

    Used for routes where only workstream_id appears in the URL.
    """
    ws_repo = WorkstreamRepository(db)
    workstream = await ws_repo.get_by_id(workstream_id)
    if workstream is None:
        raise NotFoundError(f"Workstream {workstream_id} not found")

    access_repo = ProjectAccessRepository(db)
    access = await access_repo.get_user_permission(user.id, workstream.project_id)
    if not access or permission_level(access.permission) < permission_level(min_permission):
        raise ForbiddenError("Insufficient permissions")
