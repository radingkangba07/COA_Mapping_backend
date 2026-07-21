from enum import IntEnum
from typing import Any, NamedTuple
from uuid import UUID

from coa_db_models.projects.models import Project
from coa_db_models.workstreams.models import Workstream, WorkstreamCategory, WorkstreamStage, WorkstreamStatusLog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_repository import BaseRepository


class StageDefinition(NamedTuple):
    name: str
    sequence: int
    weight: int


class StageSequence(IntEnum):
    UPLOAD_FILES = 1
    TYPE_MAPPING = 2
    ACCOUNT_MAPPING_1 = 3
    ACCOUNT_MAPPING_2 = 4
    ACCOUNT_MAPPING_3 = 5
    PREVIEW_AND_EXPORT = 6


class StageWeight(IntEnum):
    HIGH = 30
    LOW = 10


# Default stages seeded on every new workstream. Weights sum to 100.
# Applies to all connection methods (CSV and MCP).
DEFAULT_STAGES: list[StageDefinition] = [
    StageDefinition("Upload Files", StageSequence.UPLOAD_FILES, StageWeight.HIGH),
    StageDefinition("Type Mapping", StageSequence.TYPE_MAPPING, StageWeight.HIGH),
    StageDefinition("Account Mapping: 1", StageSequence.ACCOUNT_MAPPING_1, StageWeight.LOW),
    StageDefinition("Account Mapping: 2", StageSequence.ACCOUNT_MAPPING_2, StageWeight.LOW),
    StageDefinition("Account Mapping: 3", StageSequence.ACCOUNT_MAPPING_3, StageWeight.LOW),
    StageDefinition("Preview & Export", StageSequence.PREVIEW_AND_EXPORT, StageWeight.LOW),
]


class WorkstreamCategoryRepository(BaseRepository[WorkstreamCategory]):
    model = WorkstreamCategory

    async def list_ordered(self) -> list[WorkstreamCategory]:
        result = await self.session.execute(select(WorkstreamCategory).order_by(WorkstreamCategory.display_order))
        return list(result.scalars().all())


class WorkstreamRepository(BaseRepository[Workstream]):
    model = Workstream

    async def list_by_project(self, project_id: UUID) -> list[Any]:
        """Return rows of (Workstream, category_name) ordered by category display_order then display_code."""
        result = await self.session.execute(
            select(Workstream, WorkstreamCategory.name.label("category_name"))
            .join(WorkstreamCategory, Workstream.category_id == WorkstreamCategory.id)
            .where(Workstream.project_id == project_id)
            .order_by(WorkstreamCategory.display_order, Workstream.display_code)
        )
        return list(result.all())

    async def get_with_category_name(self, workstream_id: UUID) -> Any | None:
        result = await self.session.execute(
            select(Workstream, WorkstreamCategory.name.label("category_name"))
            .join(WorkstreamCategory, Workstream.category_id == WorkstreamCategory.id)
            .where(Workstream.id == workstream_id)
        )
        return result.one_or_none()

    async def get_with_project(self, workstream_id: UUID) -> tuple[Workstream, Project] | None:
        """Return (Workstream, Project) for the context endpoint."""
        result = await self.session.execute(
            select(Workstream, Project)
            .join(Project, Workstream.project_id == Project.id)
            .where(Workstream.id == workstream_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return (row[0], row[1])

    async def next_display_seq(self, project_id: UUID, category_id: UUID) -> int:
        """Return the next sequence number for display_code generation.

        Locks matching rows FOR UPDATE so concurrent inserts on the same
        project+category cannot claim the same sequence number.
        """
        result = await self.session.execute(
            select(Workstream.display_code)
            .where(Workstream.project_id == project_id, Workstream.category_id == category_id)
            .with_for_update()
        )
        codes = [row[0] for row in result.all()]
        if not codes:
            return 1
        return max(int(code.split("-")[1]) for code in codes) + 1

    async def has_stages(self, workstream_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(WorkstreamStage).where(WorkstreamStage.workstream_id == workstream_id)
        )
        return (result.scalar() or 0) > 0

    async def has_status_logs(self, workstream_id: UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(WorkstreamStatusLog)
            .where(WorkstreamStatusLog.workstream_id == workstream_id)
        )
        return (result.scalar() or 0) > 0

    async def create_with_stages(
        self,
        project_id: UUID,
        category_id: UUID,
        name: str,
        display_code: str,
        created_by: UUID,
    ) -> Workstream:
        workstream = Workstream(
            project_id=project_id,
            category_id=category_id,
            name=name,
            display_code=display_code,
            status="not_started",
            current_stage=DEFAULT_STAGES[0].name,
            created_by=created_by,
        )
        self.session.add(workstream)
        await self.session.flush()
        await self.session.refresh(workstream)

        for stage in DEFAULT_STAGES:
            self.session.add(
                WorkstreamStage(
                    workstream_id=workstream.id,
                    name=stage.name,
                    sequence=stage.sequence,
                    weight=stage.weight,
                    is_completed=False,
                )
            )
        await self.session.flush()

        return workstream


class StageRepository(BaseRepository[WorkstreamStage]):
    model = WorkstreamStage

    async def list_by_workstream(self, workstream_id: UUID) -> list[WorkstreamStage]:
        result = await self.session.execute(
            select(WorkstreamStage)
            .where(WorkstreamStage.workstream_id == workstream_id)
            .order_by(WorkstreamStage.sequence)
        )
        return list(result.scalars().all())


class StatusLogRepository(BaseRepository[WorkstreamStatusLog]):
    model = WorkstreamStatusLog

    async def list_by_workstream(self, workstream_id: UUID) -> list[Any]:
        """Return (WorkstreamStatusLog, changed_by_name) tuples ordered newest-first."""
        from coa_db_models.auth.models import User

        result = await self.session.execute(
            select(WorkstreamStatusLog, User.name.label("changed_by_name"))
            .outerjoin(User, WorkstreamStatusLog.actor_id == User.id)
            .where(WorkstreamStatusLog.workstream_id == workstream_id)
            .order_by(WorkstreamStatusLog.created_at.desc())
        )
        return list(result.all())


def make_repositories(
    session: AsyncSession,
) -> tuple[WorkstreamCategoryRepository, WorkstreamRepository, StageRepository]:
    return (
        WorkstreamCategoryRepository(session),
        WorkstreamRepository(session),
        StageRepository(session),
    )
