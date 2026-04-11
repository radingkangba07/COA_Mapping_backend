import logging
from uuid import UUID

from sqlalchemy import func, select

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.modules.auth.models import User
from src.modules.mappings.models import Mapping
from src.modules.projects.models import Company, Project, ProjectAccess
from src.modules.projects.protocols import (
    CompanyRepositoryProtocol,
    ProjectAccessRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from src.modules.projects.schemas import (
    AccessResponse,
    DashboardCompanyResponse,
    DashboardProjectResponse,
    ProjectCreate,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {"viewer": 1, "editor": 2, "approver": 3, "admin": 4}


def permission_level(perm: str) -> int:
    return PERMISSION_LEVELS.get(perm, 0)


class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepositoryProtocol,
        access_repo: ProjectAccessRepositoryProtocol,
        company_repo: CompanyRepositoryProtocol,
        session=None,
    ):
        self.project_repo = project_repo
        self.access_repo = access_repo
        self.company_repo = company_repo
        self.session = session

    async def create_project(self, data: ProjectCreate, user: User) -> Project:
        company = await self.company_repo.get_or_create(data.company_id, data.company_name)
        project = await self.project_repo.create_project(
            company_id=company.id,
            name=data.name,
            description=data.description,
            source_system=data.source_system,
            target_system=data.target_system,
            created_by=user.id,
            updated_by=user.id,
        )
        await self.access_repo.grant(
            user_id=user.id,
            project_id=project.id,
            permission="admin",
            assigned_by=user.id,
        )
        if self.session:
            await self.session.commit()
        logger.info("Project '%s' created by user %s", project.name, user.id)
        return project

    async def get_project(self, project_id: UUID) -> Project:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def list_projects(self, user: User, skip: int = 0, limit: int = 50) -> list[Project]:
        access_list = await self.access_repo.list_for_user(user.id)
        project_ids = [a.project_id for a in access_list]
        if not project_ids:
            return []
        return await self.project_repo.list_by_ids(project_ids)

    async def update_project(self, project_id: UUID, data: ProjectUpdate, user: User | None = None) -> Project:
        project = await self.get_project(project_id)
        update_data = data.model_dump(exclude_unset=True)
        allowed = {"name", "description", "status", "current_step", "source_system", "target_system"}
        filtered = {k: v for k, v in update_data.items() if k in allowed}
        if not filtered and not user:
            return project
        for key, value in filtered.items():
            setattr(project, key, value)
        if user:
            project.updated_by = user.id
        if self.session:
            await self.session.flush()
            await self.session.refresh(project)
            await self.session.commit()
        return project

    async def delete_project(self, project_id: UUID) -> None:
        project = await self.get_project(project_id)
        if self.session:
            await self.session.delete(project)
            await self.session.commit()
        logger.info("Project %s deleted", project_id)

    async def grant_access(self, project_id: UUID, user_id: UUID, permission: str, granter: User) -> ProjectAccess:
        await self.get_project(project_id)
        result = await self.access_repo.grant(
            user_id=user_id,
            project_id=project_id,
            permission=permission,
            assigned_by=granter.id,
        )
        if self.session:
            await self.session.commit()
        logger.info("Granted '%s' access to user %s on project %s", permission, user_id, project_id)
        return result

    async def revoke_access(self, project_id: UUID, user_id: UUID) -> None:
        await self.access_repo.revoke(user_id=user_id, project_id=project_id)
        if self.session:
            await self.session.commit()
        logger.info("Revoked access for user %s on project %s", user_id, project_id)

    async def get_access_list(self, project_id: UUID) -> list[dict]:
        return await self.access_repo.list_for_project(project_id)

    async def check_permission(self, user_id: UUID, project_id: UUID, min_permission: str) -> ProjectAccess:
        access = await self.access_repo.get_user_permission(user_id, project_id)
        if not access or permission_level(access.permission) < permission_level(min_permission):
            raise ForbiddenError("Insufficient permissions")
        return access

    async def get_dashboard(self, user: User) -> list[DashboardCompanyResponse]:
        if not self.session:
            return []

        # Optimized JOIN query — no N+1
        mapping_count_subq = (
            select(func.count(Mapping.id)).where(Mapping.project_id == Project.id).correlate(Project).scalar_subquery()
        )

        result = await self.session.execute(
            select(
                Project,
                Company.id.label("company_uuid"),
                Company.slug,
                Company.name.label("company_name"),
                Company.description.label("company_description"),
                ProjectAccess.permission.label("user_permission"),
                mapping_count_subq.label("mapping_count"),
            )
            .join(ProjectAccess, ProjectAccess.project_id == Project.id)
            .join(Company, Company.id == Project.company_id)
            .where(ProjectAccess.user_id == user.id)
            .order_by(Project.updated_at.desc())
        )
        rows = result.all()

        # Group by company
        companies_map: dict[UUID, DashboardCompanyResponse] = {}
        for row in rows:
            project = row[0]
            company_uuid = row.company_uuid
            if company_uuid not in companies_map:
                companies_map[company_uuid] = DashboardCompanyResponse(
                    id=company_uuid,
                    slug=row.slug,
                    name=row.company_name,
                    description=row.company_description,
                    projects=[],
                )

            # Get access list for this project
            access_rows = await self.access_repo.list_for_project(project.id)
            access_list = [AccessResponse(**a) for a in access_rows]

            companies_map[company_uuid].projects.append(
                DashboardProjectResponse(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                    source_system=project.source_system,
                    target_system=project.target_system,
                    status=project.status,
                    current_step=project.current_step,
                    created_by=project.created_by,
                    updated_by=project.updated_by,
                    created_at=project.created_at,
                    updated_at=project.updated_at,
                    user_permission=row.user_permission,
                    mapping_count=row.mapping_count or 0,
                    access_list=access_list,
                )
            )

        return list(companies_map.values())

    async def get_project_detail(self, project_id: UUID, user: User) -> dict:
        """Get detailed project info matching legacy response shape."""
        project = await self.get_project(project_id)

        # Get company
        company = await self.company_repo.get_by_id(project.company_id)

        # Get user permission
        access = await self.access_repo.get_user_permission(user.id, project_id)
        user_permission = access.permission if access else "viewer"

        # Get access list with user details
        access_rows = await self.access_repo.list_for_project(project_id)
        access_list = []
        for a in access_rows:
            access_list.append(
                {
                    "user_id": str(a["user_id"]),
                    "user_name": a.get("user_name", ""),
                    "permission": a["permission"],
                    "assigned_at": str(a["created_at"]),
                }
            )

        # Get mappings
        mappings = await self.session.execute(select(Mapping).where(Mapping.project_id == project_id))
        mapping_list = mappings.scalars().all()

        # Get mapping stats
        stats = {"total": 0, "suggested": 0, "approved": 0, "rejected": 0, "modified": 0}
        for m in mapping_list:
            stats["total"] += 1
            if m.status in stats:
                stats[m.status] += 1

        # Get created_by name
        from src.modules.auth.models import User as UserModel

        creator = await self.session.get(UserModel, project.created_by)
        created_by_name = creator.name if creator else None

        return {
            "id": str(project.id),
            "company_id": str(project.company_id),
            "name": project.name,
            "description": project.description,
            "source_system": project.source_system,
            "target_system": project.target_system,
            "status": project.status,
            "current_step": project.current_step,
            "created_by": str(project.created_by),
            "updated_by": str(project.updated_by) if project.updated_by else None,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "company": {
                "id": str(company.id),
                "slug": company.slug,
                "name": company.name,
                "description": company.description,
            }
            if company
            else {},
            "user_permission": user_permission,
            "access_list": access_list,
            "mappings": [
                {
                    "id": str(m.id),
                    "project_id": str(m.project_id),
                    "source_account_number": m.source_account_number or "",
                    "source_account_name": m.source_account_name,
                    "source_account_type": m.source_account_type or "",
                    "target_account_number": m.target_account_number or "",
                    "target_account_name": m.target_account_name or "",
                    "target_account_type": m.target_account_type or "",
                    "confidence_score": m.confidence_score,
                    "status": m.status,
                    "remark": m.remark,
                    "created_at": m.created_at.isoformat(),
                }
                for m in mapping_list
            ],
            "mapping_count": len(mapping_list),
            "created_by_name": created_by_name,
            "mapping_stats": stats,
        }

    async def create_company(self, slug: str, name: str, description: str | None = None) -> Company:
        existing = await self.company_repo.get_by_slug(slug)
        if existing:
            raise ConflictError("Company slug already exists")
        company = Company(slug=slug, name=name, description=description)
        if self.session:
            self.session.add(company)
            await self.session.flush()
            await self.session.refresh(company)
            await self.session.commit()
        return company

    async def list_companies(self, user: User) -> list[Company]:
        access_list = await self.access_repo.list_for_user(user.id)
        project_ids = [a.project_id for a in access_list]
        if not project_ids:
            return []
        projects = await self.project_repo.list_by_ids(project_ids)
        company_ids = list({p.company_id for p in projects})
        return await self.company_repo.list_by_ids(company_ids)
