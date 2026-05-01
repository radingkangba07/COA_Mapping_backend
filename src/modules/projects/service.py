import logging
from typing import Any
from uuid import UUID

from coa_db_models.auth.models import Organization, User
from coa_db_models.mappings.models import CoaMapping
from coa_db_models.projects.models import Project, ProjectAccess
from sqlalchemy import select

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.modules.projects.protocols import (
    OrgMembershipReaderProtocol,
    ProjectAccessRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from src.modules.projects.schemas import (
    ProjectCreate,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {"viewer": 1, "editor": 2, "approver": 3, "admin": 4}


def permission_level(perm: str | None) -> int:
    if perm is None:
        return 0
    return PERMISSION_LEVELS.get(perm, 0)


class ProjectService:
    def __init__(
        self,
        project_repo: ProjectRepositoryProtocol,
        access_repo: ProjectAccessRepositoryProtocol,
        session=None,
        email_service=None,
        org_repo: OrgMembershipReaderProtocol | None = None,
    ):
        self.project_repo = project_repo
        self.access_repo = access_repo
        self.session = session
        self.email_service = email_service
        self.org_repo = org_repo

    async def create_project(self, data: ProjectCreate, user: User) -> Project:
        project = await self.project_repo.create_project(
            org_id=data.resolved_org_id,
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

    async def list_projects(
        self,
        user: User,
        skip: int = 0,
        limit: int = 50,
        org_id: UUID | None = None,
    ) -> list[dict]:
        access_list = await self.access_repo.list_for_user(user.id)
        if not access_list:
            return []
        perms: dict[UUID, str] = {a.project_id: a.permission for a in access_list}
        rows = await self.project_repo.list_by_ids_with_users(list(perms.keys()))

        results: list[dict] = []
        for row in rows:
            project: Project = row[0]
            if org_id is not None and project.org_id != org_id:
                continue
            results.append(self._project_row_to_dict(row, perms.get(project.id)))

        results.sort(key=lambda p: p["updated_at"], reverse=True)
        return results[skip : skip + limit]

    async def get_project_with_users(self, project_id: UUID) -> dict:
        row = await self.project_repo.get_by_id_with_users(project_id)
        if not row:
            raise NotFoundError("Project not found")
        return self._project_row_to_dict(row)

    @staticmethod
    def _project_row_to_dict(row: Any, effective_permission: str | None = None) -> dict:
        project: Project = row[0]
        return {
            "id": project.id,
            "org_id": project.org_id,
            "name": project.name,
            "description": project.description,
            "source_system": project.source_system,
            "target_system": project.target_system,
            "status": project.status,
            "current_step": project.current_step,
            "created_by": project.created_by,
            "created_by_name": row.created_by_name,
            "updated_by": project.updated_by,
            "updated_by_name": row.updated_by_name,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "effective_permission": effective_permission,
        }

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

    async def grant_access(
        self,
        project_id: UUID,
        email: str,
        permission: str,
        granter: User,
        background_tasks=None,
    ) -> ProjectAccess:
        project = await self.get_project(project_id)
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(self.session)
        target_user = await user_repo.get_by_email(email)
        if not target_user:
            raise NotFoundError(f"User with email '{email}' not found")
        if target_user.id == granter.id:
            raise ConflictError("Cannot grant project access to yourself")
        if self.org_repo is not None:
            member = await self.org_repo.get_member(project.org_id, target_user.id)
            if member is None:
                raise ForbiddenError(
                    f"User '{email}' is not a member of this project's organization. "
                    "Invite them to the organization first."
                )
        result = await self.access_repo.grant(
            user_id=target_user.id,
            project_id=project_id,
            permission=permission,
            assigned_by=granter.id,
        )
        if self.session:
            await self.session.commit()
        logger.info("Granted '%s' access to user %s on project %s", permission, target_user.id, project_id)

        if self.email_service and background_tasks:
            granter_name = getattr(granter, "name", None) or granter.email
            background_tasks.add_task(
                self.email_service.send_project_access_email,
                to=email,
                granter_name=granter_name,
                project_name=project.name,
                permission=permission,
            )
        return result

    async def update_access(self, project_id: UUID, user_id: UUID, permission: str, granter: User) -> ProjectAccess:
        if user_id == granter.id:
            raise ConflictError("Cannot change your own access on a project")
        existing = await self.access_repo.get_user_permission(user_id, project_id)
        if not existing:
            raise NotFoundError(f"User {user_id} has no access on project {project_id}")
        result = await self.access_repo.grant(
            user_id=user_id,
            project_id=project_id,
            permission=permission,
            assigned_by=granter.id,
        )
        if self.session:
            await self.session.commit()
        logger.info("Updated access to '%s' for user %s on project %s", permission, user_id, project_id)
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

    async def get_project_detail(self, project_id: UUID, user: User) -> dict:
        row = await self.project_repo.get_by_id_with_users(project_id)
        if not row:
            raise NotFoundError("Project not found")
        project: Project = row[0]
        created_by_name: str | None = row.created_by_name
        updated_by_name: str | None = row.updated_by_name

        org = await self.session.get(Organization, project.org_id)

        access = await self.access_repo.get_user_permission(user.id, project_id)
        user_permission = access.permission if access else "viewer"

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

        mappings = await self.session.execute(select(CoaMapping).where(CoaMapping.project_id == project_id))
        mapping_list = mappings.scalars().all()

        stats = {"total": 0, "suggested": 0, "approved": 0, "rejected": 0, "modified": 0}
        for m in mapping_list:
            stats["total"] += 1
            if m.mapping_status in stats:
                stats[m.mapping_status] += 1

        from coa_db_models.auth.models import User as UserModel

        creator = await self.session.get(UserModel, project.created_by)
        created_by_name = creator.name if creator else None

        return {
            "id": str(project.id),
            "org_id": str(project.org_id),
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
            "organization": {
                "id": str(org.id),
                "slug": org.slug,
                "name": org.name,
                "description": org.description,
            }
            if org
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
                    "status": m.mapping_status,
                    "remark": m.mapping_source,
                    "created_at": m.created_at.isoformat(),
                }
                for m in mapping_list
            ],
            "mapping_count": len(mapping_list),
            "created_by_name": created_by_name,
            "updated_by_name": updated_by_name,
            "mapping_stats": stats,
        }
