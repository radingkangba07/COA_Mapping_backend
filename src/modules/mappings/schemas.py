import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MappingCreate(BaseModel):
    source_account_number: str | None = None
    source_account_name: str
    source_account_type: str | None = None
    target_account_number: str | None = None
    target_account_name: str | None = None
    target_account_type: str | None = None
    confidence_score: float = 0.0
    mapping_status: str = "suggested"
    mapping_source: str = "ai"
    source_to_map: dict | None = None
    notes: str | None = None


class MappingUpdate(BaseModel):
    source_account_number: str | None = None
    source_account_name: str | None = None
    source_account_type: str | None = None
    target_account_number: str | None = None
    target_account_name: str | None = None
    target_account_type: str | None = None
    confidence_score: float | None = None
    mapping_status: str | None = None
    mapping_source: str | None = None
    notes: str | None = None


class MappingResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source_account_number: str | None = None
    source_account_name: str
    source_account_type: str | None = None
    target_account_number: str | None = None
    target_account_name: str | None = None
    target_account_type: str | None = None
    confidence_score: float
    mapping_status: str
    mapping_source: str
    source_to_map: dict | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MappingBulkSaveResponse(BaseModel):
    success: bool = True
    mapping_count: int
    project_id: uuid.UUID


class MappingBulkUpdate(BaseModel):
    mapping_ids: list[uuid.UUID]
    updates: MappingUpdate


class MappingStatsResponse(BaseModel):
    total: int = 0
    suggested: int = 0
    approved: int = 0
    rejected: int = 0
    modified: int = 0


class HierarchicalMappingRequest(BaseModel):
    project_id: uuid.UUID
    source_file_id: uuid.UUID
    target_file_id: uuid.UUID
    mapping_file_id: uuid.UUID | None = None
    account_type_mapping_file_id: uuid.UUID | None = None


class HierarchicalMappingResponse(BaseModel):
    job_id: uuid.UUID
    project_id: uuid.UUID
    status: str


class FuzzyMatchRequest(BaseModel):
    source_columns: list[str]
    target_system: str
    threshold: int = 60


class FuzzyMatchResponse(BaseModel):
    mappings: list = []
    target_fields: list = []
