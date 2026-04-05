from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository
from src.modules.storage.models import File


class FileRepository(BaseRepository[File]):
    model = File

    async def create_file(self, **kwargs) -> File:
        file = File(**kwargs)
        self.session.add(file)
        await self.session.flush()
        await self.session.refresh(file)
        return file

    async def list_by_project(
        self, project_id: UUID, file_type: str | None = None, include_deleted: bool = False
    ) -> list[File]:
        query = select(File).where(File.project_id == project_id)
        if not include_deleted:
            query = query.where(File.is_deleted == False)  # noqa: E712
        if file_type:
            query = query.where(File.file_type == file_type)
        query = query.order_by(File.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def soft_delete(self, file_id: UUID) -> None:
        file = await self.get_by_id(file_id)
        if file:
            file.is_deleted = True
            file.updated_at = func.now()
            await self.session.flush()
