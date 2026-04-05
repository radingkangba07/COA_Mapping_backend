from uuid import UUID

from sqlalchemy import delete, func, select, update

from src.core.base_repository import BaseRepository
from src.modules.mappings.models import Mapping
from src.modules.mappings.schemas import MappingCreate


class MappingRepository(BaseRepository[Mapping]):
    model = Mapping

    async def bulk_replace(self, project_id: UUID, mappings: list[MappingCreate]) -> int:
        # DELETE all existing mappings for this project
        await self.session.execute(delete(Mapping).where(Mapping.project_id == project_id))
        # INSERT new ones
        new_mappings = [Mapping(project_id=project_id, **m.model_dump()) for m in mappings]
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
    ) -> list[Mapping]:
        query = select(Mapping).where(Mapping.project_id == project_id)
        if status:
            query = query.where(Mapping.status == status)
        if source_type:
            query = query.where(Mapping.source_account_type == source_type)
        query = query.offset(skip).limit(limit).order_by(Mapping.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def bulk_update_status(self, mapping_ids: list[UUID], status: str) -> int:
        if not mapping_ids:
            return 0
        result = await self.session.execute(update(Mapping).where(Mapping.id.in_(mapping_ids)).values(status=status))
        await self.session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def update_by_score_range(
        self, project_id: UUID, min_score: float, max_score: float, new_status: str
    ) -> dict:
        stmt = (
            update(Mapping)
            .where(
                Mapping.project_id == project_id,
                Mapping.confidence_score >= min_score,
                Mapping.confidence_score <= max_score,
            )
            .values(status=new_status)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return {"matched": result.rowcount, "modified": result.rowcount}

    async def count_by_project(self, project_id: UUID) -> int:
        result = await self.session.execute(select(func.count(Mapping.id)).where(Mapping.project_id == project_id))
        return result.scalar_one()

    async def stats_by_status(self, project_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(Mapping.status, func.count(Mapping.id))
            .where(Mapping.project_id == project_id)
            .group_by(Mapping.status)
        )
        stats = {"total": 0, "suggested": 0, "approved": 0, "rejected": 0, "modified": 0}
        for status, count in result.all():
            stats[status] = count
            stats["total"] += count
        return stats
