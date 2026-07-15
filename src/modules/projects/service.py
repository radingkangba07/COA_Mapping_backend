import logging
from typing import Any
from uuid import UUID

from coa_db_models.auth.models import Organization, User
from coa_db_models.mappings.models import CoaMapping
from coa_db_models.projects.models import (
    Project,
    ProjectAccess,
    ProjectMasterDataSelection,
    ProjectOpeningBalanceSelection,
    ProjectWizardFields,
)
from coa_db_models.workstreams.models import WorkstreamCategory
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
    ProjectOverviewGroupItem,
    ProjectOverviewResponse,
    ProjectOverviewWorkstreamItem,
    ProjectUpdate,
)
from src.modules.workstreams.repository import WorkstreamRepository

logger = logging.getLogger(__name__)

PERMISSION_LEVELS = {"viewer": 1, "editor": 2, "approver": 3, "admin": 4}

# Maps frontend data_type / account_type slugs to (category_slug, workstream_name).
# Used by create_project_full to auto-create workstreams from scope selections.
_SCOPE_TO_WORKSTREAM: dict[str, tuple[str, str]] = {
    "chart-of-accounts": ("master_data", "Chart of Accounts"),
    "customers": ("master_data", "Customers"),
    "vendors": ("master_data", "Vendors"),
    "items": ("master_data", "Items"),
    "locations": ("master_data", "Locations"),
    "contacts": ("master_data", "Contacts"),
    "vehicles": ("master_data", "Vehicles"),
    "equipment": ("master_data", "Equipment"),
    "fixed-assets": ("master_data", "Fixed Assets"),
    "historical-balance-sheet-start": ("opening_balances", "Historical Balance Sheet Start"),
    "trial-balance-movement": ("opening_balances", "Trial Balance Movement"),
    "open-ar": ("opening_balances", "Open Accounts Receivable"),
    "open-ap": ("opening_balances", "Open Accounts Payable"),
    "stock-on-hand": ("opening_balances", "Stock on Hand"),
}

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
        """Atomic creation of a project with all wizard-form sections in one transaction."""
        from src.modules.erp.dependencies import get_erp_service

        erp_service = get_erp_service()

        # 1. Validate ERP product references against YAML catalogue
        src_pid = data.source_product_id
        if src_pid and not erp_service.get_system(src_pid):
            raise ValidationError(f"Unknown source product: '{src_pid}'")
        tgt_pid = data.target_product_id
        if tgt_pid and not erp_service.get_system(tgt_pid):
            raise ValidationError(f"Unknown target product: '{tgt_pid}'")

        # 2. In-memory compatibility check (action=create only)
        if (
            data.action == "create"
            and data.source_product_id
            and data.target_product_id
            and data.source_connection_method_id
        ):
            source = erp_service.get_system(data.source_product_id)
            if source and data.source_connection_method_id not in source.get("connection_methods", []):
                raise ValidationError(
                    f"Connection method '{data.source_connection_method_id}' is not supported by '{source['name']}'"
                )

        # 3. MCP config guard — requires mcp_connection_config on action=create
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

        # 5. Persist ERP vendor/connection fields via setattr (forward-compatible)
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

        # Persist wizard fields not yet on the external ORM Project model
        _overflow = {k: v for k, v in _erp_extra.items() if v is not None and not hasattr(project, k)}
        if _overflow:
            self.session.add(ProjectWizardFields(project_id=project.id, **_overflow))
            await self.session.flush()

        # 6. Persist master data selections
        for item in data.master_data_selections:
            self.session.add(
                ProjectMasterDataSelection(
                    project_id=project.id,
                    data_type=item.data_type,
                    selected=item.selected,
                )
            )
        if data.master_data_selections:
            await self.session.flush()

        # 7. Persist opening balance selections
        for bal_item in data.opening_balance_selections:
            self.session.add(
                ProjectOpeningBalanceSelection(
                    project_id=project.id,
                    account_type=bal_item.account_type,
                    include=bal_item.include,
                )
            )
        if data.opening_balance_selections:
            await self.session.flush()

        # 7.5 Auto-create workstreams from scope selections
        ws_items: list[tuple[str, str]] = []
        for item in data.master_data_selections:
            if item.selected:
                mapping = _SCOPE_TO_WORKSTREAM.get(item.data_type)
                if mapping:
                    ws_items.append(mapping)
        for bal_item in data.opening_balance_selections:
            if bal_item.include:
                mapping = _SCOPE_TO_WORKSTREAM.get(bal_item.account_type)
                if mapping:
                    ws_items.append(mapping)

        if ws_items:
            needed_slugs = {slug for slug, _ in ws_items}
            cat_result = await self.session.execute(
                select(WorkstreamCategory).where(WorkstreamCategory.slug.in_(needed_slugs))
            )
            categories: dict[str, WorkstreamCategory] = {cat.slug: cat for cat in cat_result.scalars().all()}
            ws_repo = WorkstreamRepository(self.session)
            for category_slug, ws_name in ws_items:
                cat = categories.get(category_slug)
                if not cat:
                    logger.warning("WorkstreamCategory slug '%s' not found — skipped", category_slug)
                    continue
                seq = await ws_repo.next_display_seq(project.id, cat.id)
                display_code = f"{cat.display_code_prefix}-{seq:03d}"
                await ws_repo.create_with_stages(
                    project_id=project.id,
                    category_id=cat.id,
                    name=ws_name,
                    display_code=display_code,
                    created_by=user.id,
                )

        # 8. Requester always admin
        await self.access_repo.grant(
            user_id=user.id,
            project_id=project.id,
            permission="admin",
            assigned_by=user.id,
        )

        # 9. Add members by email (skip failures — requester already added as admin)
        for member in data.members:
            try:
                await self.grant_access(project.id, member.email, member.permission, user)
            except Exception:
                logger.warning(
                    "Could not grant access to '%s' during project creation: skipped",
                    member.email,
                )

        # 11. Single commit — all sections or nothing
        await self.session.commit()
        logger.info("Project '%s' (full wizard) created by user %s", project.name, user.id)
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

        # Merge wizard overflow fields (stored in ProjectWizardFields when not on Project model)
        if self.session:
            wizard_row = await self.session.execute(
                select(ProjectWizardFields).where(ProjectWizardFields.project_id == project_id)
            )
            wizard = wizard_row.scalar_one_or_none()
            if wizard:
                for field in _WIZARD_FIELDS:
                    if result.get(field) is None:
                        result[field] = getattr(wizard, field, None)

            # Load master data and opening balance selections
            mds_rows = await self.session.execute(
                select(ProjectMasterDataSelection).where(ProjectMasterDataSelection.project_id == project_id)
            )
            result["master_data_selections"] = [
                {"data_type": m.data_type, "selected": m.selected} for m in mds_rows.scalars()
            ]
            obs_rows = await self.session.execute(
                select(ProjectOpeningBalanceSelection).where(ProjectOpeningBalanceSelection.project_id == project_id)
            )
            result["opening_balance_selections"] = [
                {"account_type": o.account_type, "include": o.include} for o in obs_rows.scalars()
            ]

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

    async def update_project(self, project_id: UUID, data: ProjectUpdate, user: User | None = None) -> Project:
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
        overflow: dict = {}
        for key, value in filtered.items():
            if key in _WIZARD_FIELDS and not hasattr(project, key):
                overflow[key] = value
            else:
                setattr(project, key, value)
        if overflow and self.session:
            wiz_row = await self.session.execute(
                select(ProjectWizardFields).where(ProjectWizardFields.project_id == project_id)
            )
            wizard = wiz_row.scalar_one_or_none()
            if wizard:
                for k, v in overflow.items():
                    if hasattr(wizard, k):
                        setattr(wizard, k, v)
            else:
                self.session.add(ProjectWizardFields(project_id=project_id, **overflow))
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

    async def get_project_overview(self, project_id: UUID) -> ProjectOverviewResponse:
        project = await self.project_repo.get_by_id(project_id)
        if project is None:
            raise NotFoundError("Project not found")

        ws_rows = await self.project_repo.get_overview_workstreams(project_id)

        workstream_ids = [row.Workstream.id for row in ws_rows]
        stage_counts = await self.project_repo.get_stage_counts(workstream_ids)

        groups_map: dict[str, dict] = {}
        groups_order: list[str] = []

        for row in ws_rows:
            ws = row.Workstream
            slug: str = row.category_slug

            if slug not in groups_map:
                groups_map[slug] = {"key": slug, "title": row.category_name, "workstreams": []}
                groups_order.append(slug)

            total, completed = stage_counts.get(ws.id, (0, 0))
            progress = round((completed / total) * 100) if total > 0 else 0

            groups_map[slug]["workstreams"].append(
                ProjectOverviewWorkstreamItem(
                    id=ws.id,
                    code=ws.display_code,
                    name=ws.name,
                    status=ws.status,
                    progress=progress,
                    current_stage=ws.current_stage,
                    included=True,
                )
            )

        groups = [ProjectOverviewGroupItem(**groups_map[k]) for k in groups_order]

        return ProjectOverviewResponse(
            id=project.id,
            name=project.name,
            project_code=project.display_code,
            status=project.status,
            source_erp=project.source_system,
            target_erp=project.target_system,
            source_deployment=None,
            target_deployment=None,
            last_edited_at=project.updated_at,
            groups=groups,
        )

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
