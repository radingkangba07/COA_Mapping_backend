import logging
from uuid import UUID

from coa_db_models.mappings.models import AccountTypeMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.mappings.account_types.repository import AccountTypeMappingRepository
from src.modules.mappings.account_types.schemas import (
    AccountTypeMappingBulkSave,
    AccountTypeMappingBulkSaveResponse,
    AccountTypeMappingUpdate,
)
from src.modules.projects.dependencies import ensure_project_access

logger = logging.getLogger(__name__)


class AccountTypeMappingService:
    def __init__(self, repo: AccountTypeMappingRepository, session: AsyncSession):
        self.repo = repo
        self.session = session

    async def bulk_save(
        self, project_id: UUID, data: AccountTypeMappingBulkSave, user_id: UUID
    ) -> AccountTypeMappingBulkSaveResponse:
        mappings = [m.model_dump() for m in data.type_mappings]
        count = await self.repo.bulk_replace(project_id, mappings, data.mapping_file_id, user_id)
        await self.session.commit()
        logger.info(
            "Saved %d account type mappings for project %s by user %s",
            count,
            project_id,
            user_id,
        )
        return AccountTypeMappingBulkSaveResponse(count=count, project_id=project_id)

    async def list_mappings(self, project_id: UUID) -> list[AccountTypeMapping]:
        return await self.repo.list_by_project(project_id)

    async def update_mapping(
        self, mapping_id: UUID, data: AccountTypeMappingUpdate, user_id: UUID
    ) -> AccountTypeMapping:
        mapping = await self.repo.get_by_id(mapping_id)
        if not mapping:
            raise NotFoundError("Account type mapping not found")
        await ensure_project_access(self.session, user_id, mapping.project_id, "editor")
        update_data = data.model_dump(exclude_unset=True)
        update_data["updated_by"] = user_id
        mapping = await self.repo.update(mapping, update_data)
        await self.session.commit()
        return mapping

    async def clear_mappings(self, project_id: UUID) -> int:
        count = await self.repo.delete_by_project(project_id)
        await self.session.commit()
        logger.info("Cleared %d account type mappings for project %s", count, project_id)
        return count
