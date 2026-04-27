import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    org_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None  # legacy alias for org_id
    source_system: str = ""
    target_system: str = ""
    description: str | None = None

    @property
    def resolved_org_id(self) -> uuid.UUID:
        """Return org_id, falling back to company_id for backwards compatibility."""
        result = self.org_id or self.company_id
        if not result:
            raise ValueError("Either org_id or company_id is required")
        return result


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    current_step: int | None = None
    source_system: str | None = None
    target_system: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
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
    email: str
    permission: str = "viewer"


class AccessUpdate(BaseModel):
    permission: str


class AccessResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    permission: str
    created_at: datetime
    user_email: str | None = None
    user_name: str | None = None

    model_config = ConfigDict(from_attributes=True)
