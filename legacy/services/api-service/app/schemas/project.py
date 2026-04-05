"""Project schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ProjectCreate(BaseModel):
    """Schema for creating a project."""
    name: str = Field(..., min_length=1, max_length=255)
    source_erp: str = Field(..., min_length=1, max_length=100)
    target_erp: str = Field(..., min_length=1, max_length=100)
    company_id: Optional[UUID] = None
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    source_erp: Optional[str] = Field(None, min_length=1, max_length=100)
    target_erp: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(draft|in_progress|pending_review|completed)$")


class ProjectResponse(BaseModel):
    """Schema for project response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    source_erp: str
    target_erp: str
    status: str
    company_id: Optional[UUID] = None
    description: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Schema for list of projects."""
    projects: List[ProjectResponse]
    total: int


class ProjectDetail(BaseModel):
    """Schema for detailed project response with related data."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    source_erp: str
    target_erp: str
    status: str
    company_id: Optional[UUID] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    mapping_count: int = 0
    file_count: int = 0
