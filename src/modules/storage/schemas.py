import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    storage_path: str
    file_type: str
    content_type: str
    size_bytes: int
    status: str
    columns: dict | list | None = None
    row_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_id: uuid.UUID | None = None
    file_type: str
    original_filename: str
    storage_path: str
    content_type: str
    size_bytes: int
    status: str
    is_active: bool
    columns: dict | list | None = None
    row_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileListResponse(BaseModel):
    project_id: uuid.UUID
    files: list[FileResponse]
    total: int


class SignedUrlResponse(BaseModel):
    file_id: uuid.UUID
    signed_url: str | None = None
    expires_in: int | None = None
    supported: bool = True
