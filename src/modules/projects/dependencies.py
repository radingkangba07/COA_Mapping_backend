from uuid import UUID

from coa_db_models.auth.models import User
from coa_db_models.projects.models import ProjectAccess
from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError
from src.modules.auth.dependencies import get_current_user
from src.modules.projects.repository import ProjectAccessRepository, ProjectRepository
from src.modules.projects.service import ProjectService, permission_level


def get_project_service(db: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(
        project_repo=ProjectRepository(db),
        access_repo=ProjectAccessRepository(db),
        session=db,
    )


def require_project_access(min_permission: str):
    async def _check(
        project_id: UUID = Path(...),
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> ProjectAccess:
        repo = ProjectAccessRepository(db)
        access = await repo.get_user_permission(user.id, project_id)
        if not access or permission_level(access.permission) < permission_level(min_permission):
            raise ForbiddenError("Insufficient permissions")
        return access

    return _check
