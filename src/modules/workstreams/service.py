from uuid import UUID

from coa_db_models.auth.models import User
from coa_db_models.workstreams.models import Workstream

from src.core.exceptions import ConflictError, NotFoundError
from src.modules.workstreams.repository import WorkstreamCategoryRepository, WorkstreamRepository
from src.modules.workstreams.schemas import WorkstreamCreate, WorkstreamResponse, WorkstreamUpdate


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
