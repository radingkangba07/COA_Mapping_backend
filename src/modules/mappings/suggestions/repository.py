from uuid import UUID

from coa_db_models.mappings.models import CoaMappingSuggestion
from sqlalchemy import select

from src.core.base_repository import BaseRepository


class SuggestionRepository(BaseRepository[CoaMappingSuggestion]):
    model = CoaMappingSuggestion

    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMappingSuggestion]:
        query = select(CoaMappingSuggestion).where(CoaMappingSuggestion.project_id == project_id)
        if status:
            query = query.where(CoaMappingSuggestion.mapping_status == status)
        if source_type:
            query = query.where(CoaMappingSuggestion.source_account_type == source_type)
        query = query.order_by(CoaMappingSuggestion.created_at, CoaMappingSuggestion.id).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
