import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AccountTypeMappingCreate(BaseModel):
    source_account_type: str = Field(..., min_length=1, max_length=200)
    target_account_type: str = Field(..., min_length=1, max_length=200)


class AccountTypeMappingBulkSave(BaseModel):
    type_mappings: list[AccountTypeMappingCreate]
    mapping_file_id: uuid.UUID | None = None


class AccountTypeMappingUpdate(BaseModel):
    source_account_type: str | None = Field(None, min_length=1, max_length=200)
    target_account_type: str | None = Field(None, min_length=1, max_length=200)


class AccountTypeMappingResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    mapping_file_id: uuid.UUID | None = None
    source_account_type: str
    target_account_type: str
    is_active: bool
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AccountTypeMappingBulkSaveResponse(BaseModel):
    success: bool = True
    count: int
    project_id: uuid.UUID
