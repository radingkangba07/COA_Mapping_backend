from datetime import UTC, datetime
from uuid import UUID

from coa_db_models.auth.models import User
from coa_db_models.workstreams.models import Workstream

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.modules.workstreams.repository import StageRepository, WorkstreamCategoryRepository, WorkstreamRepository
from src.modules.workstreams.schemas import (
    StageCompleteResponse,
    StageResponse,
    WorkstreamCreate,
    WorkstreamResponse,
    WorkstreamUpdate,
)


def _to_response(workstream: Workstream, category_name: str) -> WorkstreamResponse:
    return WorkstreamResponse(
        id=workstream.id,
        project_id=workstream.project_id,
        category_id=workstream.category_id,
        category_name=category_name,
        display_code=workstream.display_code,
        name=workstream.name,
        status=workstream.status,
        current_stage=workstream.current_stage,
        created_at=workstream.created_at,
    )


class WorkstreamService:
    def __init__(
        self,
        category_repo: WorkstreamCategoryRepository,
        workstream_repo: WorkstreamRepository,
        session,
    ):
        self.category_repo = category_repo
        self.workstream_repo = workstream_repo
        self.session = session

    async def create(self, project_id: UUID, data: WorkstreamCreate, user: User) -> WorkstreamResponse:
        category = await self.category_repo.get_by_id(data.category_id)
        if category is None:
            raise NotFoundError(f"WorkstreamCategory {data.category_id} not found")

        seq = await self.workstream_repo.next_display_seq(project_id, data.category_id)
        display_code = f"{category.display_code_prefix}-{seq:03d}"

        workstream = await self.workstream_repo.create_with_stages(
            project_id=project_id,
            category_id=data.category_id,
            name=data.name,
            display_code=display_code,
            created_by=user.id,
        )
        await self.session.commit()
        await self.session.refresh(workstream)

        return _to_response(workstream, category.name)

    async def list(self, project_id: UUID) -> list[WorkstreamResponse]:
        rows = await self.workstream_repo.list_by_project(project_id)
        return [_to_response(ws, cat_name) for ws, cat_name in rows]

    async def update(self, workstream_id: UUID, data: WorkstreamUpdate) -> WorkstreamResponse:
        row = await self.workstream_repo.get_with_category_name(workstream_id)
        if row is None:
            raise NotFoundError(f"Workstream {workstream_id} not found")
        workstream, category_name = row

        if data.name is not None:
            workstream.name = data.name
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(workstream)

        return _to_response(workstream, category_name)

    async def delete(self, workstream_id: UUID) -> None:
        workstream = await self.workstream_repo.get_by_id(workstream_id)
        if workstream is None:
            raise NotFoundError(f"Workstream {workstream_id} not found")

        if await self.workstream_repo.has_stages(workstream_id):
            raise ConflictError("Cannot delete workstream with existing stages. Remove stages first.")
        if await self.workstream_repo.has_status_logs(workstream_id):
            raise ConflictError("Cannot delete workstream with existing status log entries.")

        await self.session.delete(workstream)
        await self.session.commit()


class StageService:
    def __init__(self, workstream_repo: WorkstreamRepository, stage_repo: StageRepository, session):
        self.workstream_repo = workstream_repo
        self.stage_repo = stage_repo
        self.session = session

    async def list_stages(self, workstream_id: UUID) -> list[StageResponse]:
        workstream = await self.workstream_repo.get_by_id(workstream_id)
        if workstream is None:
            raise NotFoundError(f"Workstream {workstream_id} not found")
        stages = await self.stage_repo.list_by_workstream(workstream_id)
        return [StageResponse.model_validate(s) for s in stages]

    async def complete_stage(self, workstream_id: UUID, stage_id: UUID, user: User) -> StageCompleteResponse:
        workstream = await self.workstream_repo.get_by_id(workstream_id)
        if workstream is None:
            raise NotFoundError(f"Workstream {workstream_id} not found")

        stage = await self.stage_repo.get_by_id(stage_id)
        if stage is None or stage.workstream_id != workstream_id:
            raise NotFoundError(f"Stage {stage_id} not found on workstream {workstream_id}")

        # Idempotent — already complete is fine
        if stage.is_completed:
            return StageCompleteResponse(
                id=stage.id,
                is_completed=True,
                completed_at=stage.completed_at,
                completed_by=stage.completed_by,
            )

        # Enforce sequential completion
        if stage.sequence > 1:
            all_stages = await self.stage_repo.list_by_workstream(workstream_id)
            prior_incomplete = [s for s in all_stages if s.sequence < stage.sequence and not s.is_completed]
            if prior_incomplete:
                raise ValidationError("Previous stage not yet completed")

        now = datetime.now(UTC)
        stage.is_completed = True
        stage.completed_at = now
        stage.completed_by = user.id

        # Update workstream.current_stage to the next incomplete stage name.
        # current_stage is NOT NULL in the DB — when all stages are done we
        # keep the last stage's name; the overview layer derives null from that.
        all_stages = await self.stage_repo.list_by_workstream(workstream_id)
        next_stage = next(
            (s for s in all_stages if not s.is_completed and s.id != stage.id),
            None,
        )
        if next_stage is not None:
            workstream.current_stage = next_stage.name

        await self.session.flush()
        await self.session.commit()
        await self.session.refresh(stage)

        return StageCompleteResponse(
            id=stage.id,
            is_completed=True,
            completed_at=stage.completed_at,
            completed_by=stage.completed_by,
        )
