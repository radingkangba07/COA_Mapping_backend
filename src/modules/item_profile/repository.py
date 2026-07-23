from datetime import datetime
from uuid import UUID

from coa_db_models.profiling.models import ItemFieldProfile, ItemProfileRun
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession


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
        await self.session.flush()


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
