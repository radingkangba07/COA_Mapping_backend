import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    project_id: uuid.UUID
    job_type: str
    input_data: dict | None = None
    source_file_id: uuid.UUID | None = None
    target_file_id: uuid.UUID | None = None
    mapping_file_id: uuid.UUID | None = None
    account_type_mapping_file_id: uuid.UUID | None = None


class JobResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: str
    progress: float
    message: str | None = None
    input_data: dict | None = None
    result_data: dict | None = None
    error_message: str | None = None
    source_file_id: uuid.UUID | None = None
    target_file_id: uuid.UUID | None = None
    mapping_file_id: uuid.UUID | None = None
    account_type_mapping_file_id: uuid.UUID | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    progress: float
    is_complete: bool
    has_error: bool


class JobResultResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    result_data: dict | None = None
    error_message: str | None = None
