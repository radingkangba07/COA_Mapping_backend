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
    status: str = "suggested"
    remark: str = "ai"
    source_row_data: dict | None = None
    notes: str | None = None


class MappingUpdate(BaseModel):
    source_account_number: str | None = None
    source_account_name: str | None = None
    source_account_type: str | None = None
    target_account_number: str | None = None
    target_account_name: str | None = None
    target_account_type: str | None = None
    confidence_score: float | None = None
    status: str | None = None
    remark: str | None = None
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
    status: str
    remark: str
    source_row_data: dict | None = None
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
    source_data: list[dict]
    target_data: list[dict] | None = None
    source_erp: str
    target_erp: str


class HierarchicalMappingResponse(BaseModel):
    type_column: str | None = None
    name_column: str | None = None
    number_column: str | None = None
    target_types: list = []
    grouped_mappings: list = []
    total_accounts: int = 0
    total_types: int = 0


class FuzzyMatchRequest(BaseModel):
    source_columns: list[str]
    target_erp: str
    threshold: int = 60


class FuzzyMatchResponse(BaseModel):
    mappings: list = []
    target_fields: list = []
