"""Company schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class CompanyCreate(BaseModel):
    """Schema for creating a company."""
    company_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class CompanyResponse(BaseModel):
    """Schema for company response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    company_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime


class CompanyWithProjects(BaseModel):
    """Schema for company with its projects."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    company_id: str
    name: str
    description: Optional[str] = None
    projects: List["ProjectBrief"] = []


class ProjectBrief(BaseModel):
    """Brief project info for company listing."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    source_erp: str
    target_erp: str
    status: str
    created_at: datetime
    updated_at: datetime


# Update forward references
CompanyWithProjects.model_rebuild()
