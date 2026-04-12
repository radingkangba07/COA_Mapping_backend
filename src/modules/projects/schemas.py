import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class CompanyResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    company_id: str  # slug
    source_system: str = ""
    target_system: str = ""
    company_name: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    current_step: int | None = None
    source_system: str | None = None
    target_system: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None = None
    source_system: str
    target_system: str
    status: str
    current_step: int = 0
    created_by: uuid.UUID
    created_by_name: str | None = None
    updated_by: uuid.UUID | None = None
    updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


class AccessGrant(BaseModel):
    user_id: uuid.UUID
    permission: str = "viewer"


class AccessResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    permission: str
    created_at: datetime
    user_email: str | None = None
    user_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DashboardProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    source_system: str
    target_system: str
    status: str
    current_step: int = 0
    created_by: uuid.UUID
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    user_permission: str
    mapping_count: int = 0
    access_list: list[AccessResponse] = []

    model_config = ConfigDict(from_attributes=True)


class DashboardCompanyResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None = None
    projects: list[DashboardProjectResponse] = []


class DashboardResponse(BaseModel):
    companies: list[DashboardCompanyResponse]
    total_projects: int
