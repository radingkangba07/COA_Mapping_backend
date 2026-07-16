import io
import logging
import uuid as uuid_mod
from pathlib import Path
from uuid import UUID

import pandas as pd
from coa_db_models.storage.models import File
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import NotFoundError
from src.modules.projects.dependencies import authorize_for_resource, ensure_project_access
from src.modules.storage.protocols import ObjectStoreProtocol
from src.modules.storage.repository import FileRepository
from src.modules.storage.s3_provider import MIME_TYPES

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, store: ObjectStoreProtocol | None, file_repo: FileRepository, session: AsyncSession):
        self.store = store
        self.file_repo = file_repo
        self.session = session

    def _build_storage_path(
        self, org_slug: str, project_id: UUID, filename: str, file_type: str, job_id: UUID | None = None
    ) -> str:
        settings = get_settings()
        ext = Path(filename).suffix
        unique_name = f"{uuid_mod.uuid4()}{ext}"
        if job_id:
            return f"{settings.app_name}/org/{org_slug}/project/{project_id}/jobs/{job_id}/{unique_name}"
        folder = "artifacts" if file_type == "artifact" else "uploads"
        return f"{settings.app_name}/org/{org_slug}/project/{project_id}/{folder}/{unique_name}"

    def _detect_content_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        return MIME_TYPES.get(ext, "application/octet-stream")

    async def upload_file(
        self,
        file_data: bytes,
        filename: str,
        project_id: UUID,
        file_type: str,
        user_id: UUID,
        org_slug: str = "default",
        uploaded_by: UUID | None = None,
        job_id: UUID | None = None,
        workstream_id: UUID | None = None,
    ) -> File:
        await ensure_project_access(self.session, user_id, project_id, "editor")
        content_type = self._detect_content_type(filename)
        storage_path = self._build_storage_path(org_slug, project_id, filename, file_type, job_id)

        # Upload to S3
        if self.store:
            self.store.put_object(storage_path, file_data, content_type)

        # Parse Excel/CSV for columns + row_count
        columns = None
        row_count = 0
        ext = Path(filename).suffix.lower()
        try:
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(io.BytesIO(file_data))
                columns = list(df.columns)
                row_count = len(df)
            elif ext == ".csv":
                df = pd.read_csv(io.BytesIO(file_data))
                columns = list(df.columns)
                row_count = len(df)
        except Exception:
            logger.warning("Failed to parse file metadata for '%s'", filename, exc_info=True)

        file = await self.file_repo.create_file(
            project_id=project_id,
            job_id=job_id,
            workstream_id=workstream_id,
            file_type=file_type,
            original_filename=filename,
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=len(file_data),
            status="ready",
            columns=columns,
            row_count=row_count,
            uploaded_by=uploaded_by,
        )
        await self.session.commit()
        logger.info("File '%s' uploaded to project %s (%d bytes)", filename, project_id, len(file_data))
        return file

    async def download_file(self, file_id: UUID, user_id: UUID) -> tuple[bytes, str, str]:
        file = await self.file_repo.get_by_id(file_id)
        await authorize_for_resource(file, self.session, user_id, "viewer", "File not found")
        assert file is not None
        if not file.is_active:
            raise NotFoundError("File not found")
        if not self.store:
            raise NotFoundError("Storage not available")
        data, content_type = self.store.get_object(file.storage_path)
        return data, content_type, file.original_filename

    async def get_signed_url(self, file_id: UUID, user_id: UUID, expires_in: int = 3600) -> str | None:
        file = await self.file_repo.get_by_id(file_id)
        await authorize_for_resource(file, self.session, user_id, "viewer", "File not found")
        assert file is not None
        if not file.is_active:
            raise NotFoundError("File not found")
        if not self.store:
            return None
        return self.store.get_signed_url(file.storage_path, expires_in)

    async def get_file(self, file_id: UUID, user_id: UUID) -> File:
        file = await self.file_repo.get_by_id(file_id)
        await authorize_for_resource(file, self.session, user_id, "viewer", "File not found")
        assert file is not None
        if not file.is_active:
            raise NotFoundError("File not found")
        return file

    async def list_files(self, project_id: UUID, file_type: str | None = None) -> list[File]:
        return await self.file_repo.list_by_project(project_id, file_type)

    async def delete_file(self, file_id: UUID, user_id: UUID) -> None:
        file = await self.file_repo.get_by_id(file_id)
        await authorize_for_resource(file, self.session, user_id, "editor", "File not found")
        assert file is not None
        if not file.is_active:
            raise NotFoundError("File not found")
        await self.file_repo.soft_delete(file_id)
        # S3 delete happens immediately. To support undo/recovery in the future,
        # move this to a scheduled cleanup job (e.g., delete from S3 after 30 days).
        if self.store:
            self.store.delete_object(file.storage_path)
        await self.session.commit()
        logger.info("File %s deleted", file_id)
