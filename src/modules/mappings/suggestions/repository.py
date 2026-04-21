from uuid import UUID

from coa_db_models.mappings.models import CoaMapping, CoaMappingSuggestion
from sqlalchemy import func, or_, select

from src.core.base_repository import BaseRepository


class SuggestionRepository(BaseRepository[CoaMappingSuggestion]):
    model = CoaMappingSuggestion

    def _base_query(
        self,
        project_id: UUID,
        status: str | None,
        source_type: str | None,
    ):
        # Three states per suggestion:
        #   - coa_mapping_id NULL                       → pending (show ML values)
        #   - coa_mapping_id set, mapping.is_active=t   → confirmed (show mapping values)
        #   - coa_mapping_id set, mapping.is_active=f   → rejected (hide)
        query = (
            select(CoaMappingSuggestion, CoaMapping)
            .outerjoin(
                CoaMapping,
                (CoaMapping.id == CoaMappingSuggestion.coa_mapping_id) & (CoaMapping.is_active.is_(True)),
            )
            .where(
                CoaMappingSuggestion.project_id == project_id,
                or_(CoaMappingSuggestion.coa_mapping_id.is_(None), CoaMapping.id.is_not(None)),
            )
        )
        if status:
            query = query.where(CoaMappingSuggestion.mapping_status == status)
        if source_type:
            query = query.where(CoaMappingSuggestion.source_account_type == source_type)
        return query

    async def list_by_project_with_mappings(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[tuple[CoaMappingSuggestion, CoaMapping | None]]:
        query = (
            self._base_query(project_id, status, source_type)
            .order_by(CoaMappingSuggestion.created_at, CoaMappingSuggestion.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def count_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
    ) -> int:
        subq = self._base_query(project_id, status, source_type).subquery()
        result = await self.session.execute(select(func.count()).select_from(subq))
        return int(result.scalar_one())
