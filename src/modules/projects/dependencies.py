from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from coa_db_models.auth.models import User
from coa_db_models.projects.models import ProjectAccess
from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError, NotFoundError
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.email_service import EmailService
from src.modules.projects.repository import ProjectAccessRepository, ProjectRepository
from src.modules.projects.service import ProjectService, permission_level


class _HasProjectId(Protocol):
    project_id: UUID


def get_project_service(db: AsyncSession = Depends(get_db)) -> ProjectService:
    return ProjectService(
        project_repo=ProjectRepository(db),
        access_repo=ProjectAccessRepository(db),
        session=db,
        email_service=EmailService(),
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


async def ensure_project_access(
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    min_permission: str,
) -> ProjectAccess:
    """Service-layer access check for routes where project_id isn't in the URL.

    Use this inside a service method after resolving project_id from a resource
    (e.g., a mapping row). Raises ForbiddenError on fail.
    """
    repo = ProjectAccessRepository(db)
    access = await repo.get_user_permission(user_id, project_id)
    if not access or permission_level(access.permission) < permission_level(min_permission):
        raise ForbiddenError("Insufficient permissions")
    return access


async def authorize_for_resource(
    resource: _HasProjectId | None,
    db: AsyncSession,
    user_id: UUID,
    min_permission: str,
    not_found_msg: str,
) -> None:
    """Raise NotFoundError if resource is None, then enforce project access.

    Use when the URL carries a resource ID (e.g., /mappings/{mapping_id}) and
    project_id must be derived from the row.
    """
    if resource is None:
        raise NotFoundError(not_found_msg)
    await ensure_project_access(db, user_id, resource.project_id, min_permission)


async def authorize_for_resources(
    resources: Iterable[_HasProjectId],
    db: AsyncSession,
    user_id: UUID,
    min_permission: str,
) -> None:
    """Enforce access on each distinct project_id across a list of resources.

    Use for bulk endpoints where IDs may span multiple projects.
    """
    for pid in {r.project_id for r in resources}:
        await ensure_project_access(db, user_id, pid, min_permission)
