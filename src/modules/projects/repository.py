from typing import Any
from uuid import UUID

from coa_db_models.auth.models import User
from coa_db_models.projects.models import Project, ProjectAccess
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def list_by_ids(self, project_ids: list[UUID]) -> list[Project]:
        if not project_ids:
            return []
        result = await self.session.execute(select(Project).where(Project.id.in_(project_ids)))
        return list(result.scalars().all())

    async def list_by_ids_with_users(self, project_ids: list[UUID]) -> list[Any]:
        if not project_ids:
            return []
        creator = aliased(User, flat=True)
        updater = aliased(User, flat=True)
        result = await self.session.execute(
            select(
                Project,
                creator.name.label("created_by_name"),
                updater.name.label("updated_by_name"),
            )
            .outerjoin(creator, Project.created_by == creator.id)
            .outerjoin(updater, Project.updated_by == updater.id)
            .where(Project.id.in_(project_ids))
            .order_by(Project.updated_at.desc())
        )
        return list(result.all())

    async def get_by_id_with_users(self, project_id: UUID) -> Any | None:
        creator = aliased(User, flat=True)
        updater = aliased(User, flat=True)
        result = await self.session.execute(
            select(
                Project,
                creator.name.label("created_by_name"),
                updater.name.label("updated_by_name"),
            )
            .outerjoin(creator, Project.created_by == creator.id)
            .outerjoin(updater, Project.updated_by == updater.id)
            .where(Project.id == project_id)
        )
        return result.one_or_none()

    async def list_by_org(self, org_id: UUID, skip: int = 0, limit: int = 50) -> list[Project]:
        result = await self.session.execute(
            select(Project).where(Project.org_id == org_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create_project(self, **kwargs) -> Project:
        project = Project(**kwargs)
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def update_status(self, project_id: UUID, status: str) -> None:
        project = await self.get_by_id(project_id)
        if project:
            project.status = status
            project.updated_at = func.now()
            await self.session.flush()


class ProjectAccessRepository:
    def __init__(self, session):
        self.session = session

    async def get_user_permission(self, user_id: UUID, project_id: UUID) -> ProjectAccess | None:
        result = await self.session.execute(
            select(ProjectAccess).where(
                ProjectAccess.user_id == user_id,
                ProjectAccess.project_id == project_id,
            )
        )
        access: ProjectAccess | None = result.scalar_one_or_none()
        return access

    async def list_for_project(self, project_id: UUID) -> list[dict]:
        result = await self.session.execute(
            select(
                ProjectAccess.id,
                ProjectAccess.user_id,
                ProjectAccess.project_id,
                ProjectAccess.permission,
                ProjectAccess.created_at,
                User.email.label("user_email"),
                User.name.label("user_name"),
            )
            .join(User, User.id == ProjectAccess.user_id)
            .where(ProjectAccess.project_id == project_id)
        )
        rows = result.all()
        return [row._asdict() for row in rows]

    async def list_for_user(self, user_id: UUID) -> list[ProjectAccess]:
        result = await self.session.execute(select(ProjectAccess).where(ProjectAccess.user_id == user_id))
        return list(result.scalars().all())

    async def grant(self, user_id: UUID, project_id: UUID, permission: str, assigned_by: UUID) -> ProjectAccess:
        stmt = insert(ProjectAccess).values(
            user_id=user_id,
            project_id=project_id,
            permission=permission,
            assigned_by=assigned_by,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_project",
            set_={"permission": permission, "assigned_by": assigned_by},
        )
        await self.session.execute(stmt)
        await self.session.flush()
        result = await self.get_user_permission(user_id, project_id)
        return result

    async def revoke(self, user_id: UUID, project_id: UUID) -> None:
        await self.session.execute(
            delete(ProjectAccess).where(
                ProjectAccess.user_id == user_id,
                ProjectAccess.project_id == project_id,
            )
        )
        await self.session.flush()
