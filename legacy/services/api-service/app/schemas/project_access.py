"""Project Access schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class ProjectAccessCreate(BaseModel):
    """Schema for creating project access."""
    user_id: UUID
    project_id: UUID
    permission: str = Field(default="viewer", pattern="^(viewer|editor|approver|admin)$")


class ProjectAccessUpdate(BaseModel):
    """Schema for updating project access."""
    permission: str = Field(..., pattern="^(viewer|editor|approver|admin)$")


class ProjectAccessResponse(BaseModel):
    """Schema for project access response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    project_id: UUID
    permission: str
    assigned_at: datetime


class ProjectAccessWithUser(BaseModel):
    """Schema for project access with user details."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    permission: str
    assigned_at: datetime
    user: "UserBrief"


class UserBrief(BaseModel):
    """Brief user info."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: str
    name: str


class ProjectWithAccess(BaseModel):
    """Schema for project with access info."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    source_erp: str
    target_erp: str
    status: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    user_permission: Optional[str] = None
    access_list: List[ProjectAccessWithUser] = []


# Update forward references
ProjectAccessWithUser.model_rebuild()
