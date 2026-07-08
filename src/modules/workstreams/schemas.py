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


# ── Stage schemas (DAB-20) ────────────────────────────────────────────────────


class StageResponse(BaseModel):
    id: uuid.UUID
    workstream_id: uuid.UUID
    name: str
    sequence: int
    is_completed: bool
    completed_at: datetime | None
    completed_by: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class StageCompleteResponse(BaseModel):
    id: uuid.UUID
    is_completed: bool
    completed_at: datetime
    completed_by: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


# ── Status schemas (DAB-21) ───────────────────────────────────────────────────


class StatusTransitionRequest(BaseModel):
    new_status: str
    note: str | None = None


class StatusLogEntry(BaseModel):
    id: uuid.UUID
    workstream_id: uuid.UUID
    previous_status: str
    new_status: str
    note: str | None
    changed_by: uuid.UUID | None
    changed_by_name: str | None
    created_at: datetime
