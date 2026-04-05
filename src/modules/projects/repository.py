from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository
from src.modules.auth.models import User
from src.modules.projects.models import Company, Project, ProjectAccess


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def get_by_slug(self, slug: str) -> Company | None:
        result = await self.session.execute(select(Company).where(Company.slug == slug))
        return result.scalar_one_or_none()

    async def get_or_create(self, slug: str, name: str | None = None) -> Company:
        company = await self.get_by_slug(slug)
        if company:
            return company
        display_name = name or slug.replace("-", " ").title()
        company = Company(slug=slug, name=display_name)
        self.session.add(company)
        await self.session.flush()
        await self.session.refresh(company)
        return company

    async def list_by_ids(self, company_ids: list[UUID]) -> list[Company]:
        if not company_ids:
            return []
        result = await self.session.execute(select(Company).where(Company.id.in_(company_ids)))
        return list(result.scalars().all())


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def list_by_ids(self, project_ids: list[UUID]) -> list[Project]:
        if not project_ids:
            return []
        result = await self.session.execute(select(Project).where(Project.id.in_(project_ids)))
        return list(result.scalars().all())

    async def list_by_company(self, company_id: UUID, skip: int = 0, limit: int = 50) -> list[Project]:
        result = await self.session.execute(
            select(Project).where(Project.company_id == company_id).offset(skip).limit(limit)
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
        return result.scalar_one_or_none()

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
        return result  # type: ignore[return-value]

    async def revoke(self, user_id: UUID, project_id: UUID) -> None:
        await self.session.execute(
            delete(ProjectAccess).where(
                ProjectAccess.user_id == user_id,
                ProjectAccess.project_id == project_id,
            )
        )
        await self.session.flush()
