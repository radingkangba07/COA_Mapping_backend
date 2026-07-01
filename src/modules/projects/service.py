import logging
from typing import Any
from uuid import UUID

from coa_db_models import ProjectMasterDataSelection, ProjectOpeningBalanceSelection, ProjectWizardFields
from coa_db_models.auth.models import Organization, User
from coa_db_models.mappings.models import CoaMapping
from coa_db_models.projects.models import Project, ProjectAccess
from sqlalchemy import select

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from src.modules.projects.protocols import (
    OrgMembershipReaderProtocol,
    ProjectAccessRepositoryProtocol,
    ProjectRepositoryProtocol,
)
from src.modules.projects.schemas import (
    ProjectCreate,
    ProjectCreateFull,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {"viewer": 1, "editor": 2, "approver": 3, "admin": 4}

# Fields added by the data-migration wizard that require a DB migration in
# coa-db-models before they can be persisted. The service sets them
# via setattr only when the ORM model already exposes them, so this code
# is forward-compatible: once the migration runs, persistence is automatic.
_WIZARD_FIELDS = (
    "source_vendor_id",
    "source_connection_method",
    "source_protocol",
    "target_vendor_id",
    "target_connection_method",
    "target_protocol",
    "migration_scope",
    "starting_balance",
    "source_date",
    "mcp_server_url",
    "mcp_api_key",
)


def permission_level(perm: str | None) -> int:
    if perm is None:
        return 0
    return PERMISSION_LEVELS.get(perm, 0)


def _apply_wizard_fields(project: Project, data: ProjectCreate | ProjectUpdate) -> None:
    """Write wizard fields onto the ORM object when the model supports them."""
    for field in _WIZARD_FIELDS:
        value = getattr(data, field, None)
        if value is None:
            continue
        if not hasattr(project, field):
            continue
        if field == "migration_scope" and not isinstance(value, (dict, list)):
            value = [item.model_dump() for item in value]
        setattr(project, field, value)


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
        _apply_wizard_fields(project, data)

        await self.access_repo.grant(
            user_id=user.id,
            project_id=project.id,
            permission="admin",
            assigned_by=user.id,
        )

        if data.members:
            for member in data.members:
                try:
                    await self.grant_access(project.id, member.email, member.permission, user)
                except Exception:
                    logger.warning(
                        "Could not grant access to '%s' during project creation: skipped",
                        member.email,
                    )

        if self.session:
            await self.session.commit()
        logger.info("Project '%s' created by user %s", project.name, user.id)
        return project

    async def create_project_full(self, data: ProjectCreateFull, user: User) -> Project:
        from src.modules.erp.dependencies import get_erp_service

        erp_service = get_erp_service()

        # 1. Validate ERP FK references
        if data.source_vendor_id and not erp_service.get_vendor(data.source_vendor_id):
            raise ValidationError(f"Unknown source vendor: '{data.source_vendor_id}'")
        if data.target_vendor_id and not erp_service.get_vendor(data.target_vendor_id):
            raise ValidationError(f"Unknown target vendor: '{data.target_vendor_id}'")
        if data.source_product_id and not erp_service.get_system(data.source_product_id):
            raise ValidationError(f"Unknown source product: '{data.source_product_id}'")
        if data.target_product_id and not erp_service.get_system(data.target_product_id):
            raise ValidationError(f"Unknown target product: '{data.target_product_id}'")

        # 2. Compatibility check (action=create only)
        if (
            data.action == "create"
            and data.source_product_id
            and data.target_product_id
            and data.source_connection_method_id
        ):
            is_compatible, message = erp_service.check_compatibility(
                data.source_product_id,
                data.target_product_id,
                data.source_connection_method_id,
            )
            if not is_compatible:
                raise ValidationError(message)

        # 3. MCP config guard
        if data.source_connection_method_id:
            conn_method = erp_service.get_connection_method(data.source_connection_method_id)
            if (
                conn_method
                and conn_method.get("requires_mcp_config")
                and data.action == "create"
                and not data.mcp_connection_config
            ):
                raise ValidationError("mcp_connection_config is required when using MCP Server connection method")

        if data.org_id is None:
            raise ValidationError("org_id is required")

        # 4. Create project row
        project = await self.project_repo.create_project(
            org_id=data.org_id,
            name=data.name,
            description=data.description,
            source_system=data.source_product_id or "",
            target_system=data.target_product_id or "",
            status="active" if data.action == "create" else "draft",
            created_by=user.id,
            updated_by=user.id,
        )

        # 5 & 6. Persist wizard-compatible ERP fields and MCP config via forward-compatible setattr
        _erp_extra: dict = {
            "source_vendor_id": data.source_vendor_id,
            "source_connection_method": data.source_connection_method_id,
            "target_vendor_id": data.target_vendor_id,
            "target_connection_method": data.target_connection_method_id,
        }
        for field, value in _erp_extra.items():
            if value is not None and hasattr(project, field):
                setattr(project, field, value)

        if data.mcp_connection_config:
            if hasattr(project, "mcp_server_url"):
                project.mcp_server_url = data.mcp_connection_config.server_url
            if hasattr(project, "mcp_api_key"):
                project.mcp_api_key = data.mcp_connection_config.api_key

        # Persist wizard fields that have no column on the external ORM model
        _wizard_row = {k: v for k, v in _erp_extra.items() if v is not None and not hasattr(project, k)}
        if _wizard_row:
            self.session.add(ProjectWizardFields(project_id=project.id, **_wizard_row))
            await self.session.flush()

        # 5a. Persist master data selections (bulk-add to session; committed below)
        if data.master_data_selections:
            for item in data.master_data_selections:
                self.session.add(
                    ProjectMasterDataSelection(
                        project_id=project.id,
                        data_type=item.data_type,
                        selected=item.selected,
                    )
                )
            await self.session.flush()

        # 5b. Persist opening balance selections
        if data.opening_balance_selections:
            for bal_item in data.opening_balance_selections:
                self.session.add(
                    ProjectOpeningBalanceSelection(
                        project_id=project.id,
                        account_type=bal_item.account_type,
                        include=bal_item.include,
                    )
                )
            await self.session.flush()

        # 7. Requester always added as admin
        await self.access_repo.grant(
            user_id=user.id,
            project_id=project.id,
            permission="admin",
            assigned_by=user.id,
        )

        # 8. Add members (skip requester — already admin above)
        for member in data.members:
            if member.user_id != user.id:
                await self.access_repo.grant(
                    user_id=member.user_id,
                    project_id=project.id,
                    permission=member.permission,
                    assigned_by=user.id,
                )

        # 9. Single commit
        if self.session:
            await self.session.commit()
            await self.session.refresh(project)

        logger.info("Project '%s' created (action=%s) by user %s", project.name, data.action, user.id)
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
        result = self._project_row_to_dict(row)

        # Overlay wizard fields (vendor IDs etc.) from the extension table
        wizard = await self.session.get(ProjectWizardFields, project_id)
        if wizard:
            result["source_vendor_id"] = wizard.source_vendor_id
            result["target_vendor_id"] = wizard.target_vendor_id
            result["source_connection_method"] = wizard.source_connection_method
            result["target_connection_method"] = wizard.target_connection_method

        # Build migration_scope from master data selections only
        master_res = await self.session.execute(
            select(ProjectMasterDataSelection).where(
                ProjectMasterDataSelection.project_id == project_id,
                ProjectMasterDataSelection.selected.is_(True),
            )
        )
        master_items = [{"type": r.data_type, "status": "not_started"} for r in master_res.scalars()]
        result["migration_scope"] = master_items if master_items else None

        # Return opening balance selections as their own field
        balance_res = await self.session.execute(
            select(ProjectOpeningBalanceSelection).where(
                ProjectOpeningBalanceSelection.project_id == project_id,
            )
        )
        balance_rows = balance_res.scalars().all()
        result["opening_balance_selections"] = (
            [{"account_type": r.account_type, "include": r.include} for r in balance_rows]
            if balance_rows
            else None
        )

        return result

    @staticmethod
    def _project_row_to_dict(row: Any, effective_permission: str | None = None) -> dict:
        project: Project = row[0]
        base = {
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
        # Include wizard fields when the ORM model supports them
        for field in _WIZARD_FIELDS:
            base[field] = getattr(project, field, None)
        return base

    async def update_project(self, project_id: UUID, data: ProjectUpdate, user: User | None = None) -> dict:
        project = await self.get_project(project_id)
        update_data = data.model_dump(exclude_unset=True)
        allowed = {
            "name",
            "description",
            "status",
            "current_step",
            "source_system",
            "target_system",
            *_WIZARD_FIELDS,
        }
        filtered = {k: v for k, v in update_data.items() if k in allowed}
        for key, value in filtered.items():
            if key in _WIZARD_FIELDS and not hasattr(project, key):
                continue
            setattr(project, key, value)
        if user:
            project.updated_by = user.id

        # Fields not on the ORM model go into the wizard fields extension table
        _external_fields = {
            "source_vendor_id",
            "target_vendor_id",
            "source_connection_method",
            "target_connection_method",
        }
        ext = {k: v for k, v in filtered.items() if k in _external_fields and not hasattr(project, k)}

        if self.session:
            await self.session.flush()
            if ext:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                stmt = (
                    pg_insert(ProjectWizardFields)
                    .values(project_id=project_id, **ext)
                    .on_conflict_do_update(index_elements=["project_id"], set_=ext)
                )
                await self.session.execute(stmt)

            if data.opening_balance_selections is not None:
                from sqlalchemy import delete

                await self.session.execute(
                    delete(ProjectOpeningBalanceSelection).where(
                        ProjectOpeningBalanceSelection.project_id == project_id
                    )
                )
                for bal in data.opening_balance_selections:
                    self.session.add(
                        ProjectOpeningBalanceSelection(
                            project_id=project_id,
                            account_type=bal.account_type,
                            include=bal.include,
                        )
                    )

            await self.session.commit()
            await self.session.refresh(project)

        result: dict = {
            "id": project.id,
            "org_id": project.org_id,
            "name": project.name,
            "description": project.description,
            "source_system": project.source_system,
            "target_system": project.target_system,
            "status": project.status,
            "current_step": project.current_step,
            "created_by": project.created_by,
            "created_by_name": None,
            "updated_by": project.updated_by,
            "updated_by_name": None,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "effective_permission": None,
        }
        for field in _WIZARD_FIELDS:
            result[field] = getattr(project, field, None)
        for k, v in ext.items():
            result[k] = v

        if data.opening_balance_selections is not None:
            result["opening_balance_selections"] = [
                {"account_type": b.account_type, "include": b.include}
                for b in data.opening_balance_selections
            ]

        return result

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
                    "Invite them to the organisation first."
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

        detail: dict = {
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
        # Include wizard fields when the ORM model supports them
        for field in _WIZARD_FIELDS:
            detail[field] = getattr(project, field, None)
        return detail
