from typing import cast
from uuid import UUID

from coa_db_models.mappings.models import AccountTypeMapping
from sqlalchemy import CursorResult, delete, select

from src.core.base_repository import BaseRepository


class AccountTypeMappingRepository(BaseRepository[AccountTypeMapping]):
    model = AccountTypeMapping

    async def bulk_replace(
        self,
        project_id: UUID,
        mappings: list[dict],
        mapping_file_id: UUID | None,
        created_by: UUID,
    ) -> int:
        await self.session.execute(delete(AccountTypeMapping).where(AccountTypeMapping.project_id == project_id))
        new_mappings = [
            AccountTypeMapping(
                project_id=project_id,
                source_account_type=m["source_account_type"],
                target_account_type=m["target_account_type"],
                mapping_file_id=mapping_file_id,
                is_active=True,
                created_by=created_by,
                updated_by=created_by,
            )
            for m in mappings
        ]
        self.session.add_all(new_mappings)
        await self.session.flush()
        return len(new_mappings)

    async def list_by_project(self, project_id: UUID) -> list[AccountTypeMapping]:
        result = await self.session.execute(
            select(AccountTypeMapping)
            .where(
                AccountTypeMapping.project_id == project_id,
                AccountTypeMapping.is_active.is_(True),
            )
            .order_by(AccountTypeMapping.source_account_type)
        )
        return list(result.scalars().all())

    async def delete_by_project(self, project_id: UUID) -> int:
        result = await self.session.execute(
            delete(AccountTypeMapping).where(AccountTypeMapping.project_id == project_id)
        )
        await self.session.flush()
        rowcount: int = cast(CursorResult, result).rowcount
        return rowcount
