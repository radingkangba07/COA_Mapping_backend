import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkstreamCreate(BaseModel):
    category_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)


class WorkstreamUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class WorkstreamResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    display_code: str
    name: str
    status: str
    current_stage: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkstreamListResponse(BaseModel):
    workstreams: list[WorkstreamResponse]
    total: int
