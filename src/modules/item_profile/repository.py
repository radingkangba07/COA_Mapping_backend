from datetime import datetime
from uuid import UUID

from coa_db_models.profiling.models import ItemFieldProfile, ItemProfileRun
from sqlalchemy import Float, case, delete, func, insert, or_, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError


class ItemProfileRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, project_id: UUID, started_at: datetime, source_file_ref: str) -> ItemProfileRun:
        run = ItemProfileRun(
            project_id=project_id,
            status="ingesting",
            started_at=started_at,
            source_file_ref=source_file_ref,
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def update_run(
        self,
        run_id: UUID,
        *,
        status: str,
        source_row_count: int | None = None,
        field_count: int | None = None,
        error_detail: str | None = None,
        completed_at: datetime | None = None,
        duplicate_summary: dict | None = None,
        cross_subsidiary_summary: dict | None = None,
    ) -> None:
        run = await self.session.get(ItemProfileRun, run_id)
        if not run:
            return
        run.status = status
        if source_row_count is not None:
            run.source_row_count = source_row_count
        if field_count is not None:
            run.field_count = field_count
        if error_detail is not None:
            run.error_detail = error_detail
        if completed_at is not None:
            run.completed_at = completed_at
        if duplicate_summary is not None:
            run.duplicate_summary = duplicate_summary
        if cross_subsidiary_summary is not None:
            run.cross_subsidiary_summary = cross_subsidiary_summary
        await self.session.flush()

    async def list_runs(self, project_id: UUID) -> list[ItemProfileRun]:
        result = await self.session.execute(
            select(ItemProfileRun)
            .where(ItemProfileRun.project_id == project_id)
            .order_by(ItemProfileRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_run(self, run_id: UUID) -> ItemProfileRun | None:
        return await self.session.get(ItemProfileRun, run_id)

    async def get_run_or_404(self, run_id: UUID) -> ItemProfileRun:
        run = await self.get_run(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")
        return run


class ItemFieldProfileRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_by_run(self, run_id: UUID) -> None:
        await self.session.execute(
            delete(ItemFieldProfile).where(ItemFieldProfile.run_id == run_id)
        )
        await self.session.flush()

    async def bulk_create(self, profiles: list[dict]) -> None:
        if not profiles:
            return
        await self.session.execute(insert(ItemFieldProfile), profiles)
        await self.session.flush()

    async def list_fields(
        self,
        run_id: UUID,
        *,
        role: str | None = None,
        severity: str | None = None,
        search: str | None = None,
        sort: str = "field_name",
        order: str = "asc",
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[ItemFieldProfile], int]:
        query = select(ItemFieldProfile).where(ItemFieldProfile.run_id == run_id)
        if role:
            query = query.where(ItemFieldProfile.semantic_role == role)
        if severity:
            query = query.where(ItemFieldProfile.severity == severity)
        if search:
            query = query.where(ItemFieldProfile.field_name.ilike(f"%{search}%"))

        _sort_cols = {
            "uniqueness_pct": sa_cast(ItemFieldProfile.stats["uniqueness_pct"].astext, Float),
            "null_pct": sa_cast(ItemFieldProfile.stats["null_pct"].astext, Float),
            "field_name": ItemFieldProfile.field_name,
        }
        sort_col = _sort_cols.get(sort, ItemFieldProfile.field_name)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

        count_result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        paged = await self.session.execute(query.offset(offset).limit(page_size))
        return list(paged.scalars().all()), total

    async def get_field(self, run_id: UUID, field_name: str) -> ItemFieldProfile | None:
        result = await self.session.execute(
            select(ItemFieldProfile).where(
                ItemFieldProfile.run_id == run_id,
                ItemFieldProfile.field_name == field_name,
            )
        )
        return result.scalar_one_or_none()

    async def get_field_or_404(self, run_id: UUID, field_name: str) -> ItemFieldProfile:
        fp = await self.get_field(run_id, field_name)
        if fp is None:
            raise NotFoundError(f"Field '{field_name}' not found in run {run_id}")
        return fp

    async def compute_coverage(self, run_id: UUID) -> dict:
        result = await self.session.execute(
            select(
                func.count(ItemFieldProfile.id).label("total_fields"),
                func.sum(ItemFieldProfile.null_count).label("total_nulls"),
                func.sum(ItemFieldProfile.total_count).label("total_values"),
                func.avg(
                    sa_cast(ItemFieldProfile.distinct_count, Float)
                    / func.nullif(ItemFieldProfile.total_count - ItemFieldProfile.null_count, 0)
                    * 100
                ).label("avg_uniqueness"),
                func.sum(
                    case(
                        (
                            or_(
                                ItemFieldProfile.anomaly_count.is_(None),
                                ItemFieldProfile.anomaly_count == 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("conforming_fields"),
            ).where(ItemFieldProfile.run_id == run_id)
        )
        row = result.one()
        if not row.total_fields:
            return {"completeness_pct": None, "uniqueness_pct": None, "pattern_conformance_pct": None}
        total_values = row.total_values or 0
        total_nulls = row.total_nulls or 0
        completeness = round(100.0 * (1 - total_nulls / total_values), 1) if total_values else 100.0
        uniqueness = round(float(row.avg_uniqueness), 1) if row.avg_uniqueness is not None else None
        conformance = round(100.0 * (row.conforming_fields or 0) / row.total_fields, 1)
        return {
            "completeness_pct": completeness,
            "uniqueness_pct": uniqueness,
            "pattern_conformance_pct": conformance,
        }
