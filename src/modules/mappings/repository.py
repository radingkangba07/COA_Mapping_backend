from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select, update

from src.core.base_repository import BaseRepository
from src.modules.mappings.models import CoaMapping
from src.modules.mappings.schemas import MappingCreate


class MappingRepository(BaseRepository[CoaMapping]):
    model = CoaMapping

    async def bulk_replace(self, project_id: UUID, mappings: list[MappingCreate]) -> int:
        await self.session.execute(delete(CoaMapping).where(CoaMapping.project_id == project_id))
        new_mappings = [CoaMapping(project_id=project_id, **m.model_dump()) for m in mappings]
        self.session.add_all(new_mappings)
        await self.session.flush()
        return len(new_mappings)

    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMapping]:
        query = select(CoaMapping).where(CoaMapping.project_id == project_id)
        if status:
            query = query.where(CoaMapping.mapping_status == status)
        if source_type:
            query = query.where(CoaMapping.source_account_type == source_type)
        query = query.offset(skip).limit(limit).order_by(CoaMapping.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def bulk_update_status(self, mapping_ids: list[UUID], status: str) -> int:
        if not mapping_ids:
            return 0
        result = await self.session.execute(
            update(CoaMapping).where(CoaMapping.id.in_(mapping_ids)).values(mapping_status=status)
        )
        await self.session.flush()
        rowcount: int = cast(CursorResult, result).rowcount
        return rowcount

    async def update_by_score_range(
        self, project_id: UUID, min_score: float, max_score: float, new_status: str
    ) -> dict:
        stmt = (
            update(CoaMapping)
            .where(
                CoaMapping.project_id == project_id,
                CoaMapping.confidence_score >= min_score,
                CoaMapping.confidence_score <= max_score,
            )
            .values(mapping_status=new_status)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        rowcount = cast(CursorResult, result).rowcount
        return {"matched": rowcount, "modified": rowcount}

    async def count_by_project(self, project_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(CoaMapping.id)).where(CoaMapping.project_id == project_id)
        )
        return result.scalar_one()

    async def stats_by_status(self, project_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(CoaMapping.mapping_status, func.count(CoaMapping.id))
            .where(CoaMapping.project_id == project_id)
            .group_by(CoaMapping.mapping_status)
        )
        stats = {"total": 0, "suggested": 0, "approved": 0, "rejected": 0, "modified": 0}
        for status, count in result.all():
            stats[status] = count
            stats["total"] += count
        return stats
