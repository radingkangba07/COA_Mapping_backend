import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MigrationScopeItem(BaseModel):
    type: str
    status: str = "not_started"
    start_date: date | None = None
    end_date: date | None = None


class MemberInvite(BaseModel):
    email: str
    permission: str = "viewer"


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    org_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None  # legacy alias for org_id
    description: str | None = None

    # ERP selection — source
    source_system: str = ""  # product id, kept for backward compatibility
    source_vendor_id: str | None = None
    source_connection_method: str | None = None
    source_protocol: str | None = None

    # ERP selection — target
    target_system: str = ""  # product id, kept for backward compatibility
    target_vendor_id: str | None = None
    target_connection_method: str | None = None
    target_protocol: str | None = None

    # Migration configuration
    migration_scope: list[MigrationScopeItem] | None = None
    starting_balance: bool = False
    source_date: date | None = None

    # MCP connection details (used when connection method is mcp_server)
    mcp_server_url: str | None = None
    mcp_api_key: str | None = None

    # Members to grant access to at creation time
    members: list[MemberInvite] | None = None

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

    # ERP selection — source
    source_system: str | None = None
    source_vendor_id: str | None = None
    source_connection_method: str | None = None
    source_protocol: str | None = None

    # ERP selection — target
    target_system: str | None = None
    target_vendor_id: str | None = None
    target_connection_method: str | None = None
    target_protocol: str | None = None

    # Migration configuration
    migration_scope: list[MigrationScopeItem] | None = None
    starting_balance: bool | None = None
    source_date: date | None = None

    # MCP connection details
    mcp_server_url: str | None = None
    mcp_api_key: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None = None

    # ERP selection — source
    source_system: str
    source_vendor_id: str | None = None
    source_connection_method: str | None = None
    source_protocol: str | None = None

    # ERP selection — target
    target_system: str
    target_vendor_id: str | None = None
    target_connection_method: str | None = None
    target_protocol: str | None = None

    # Migration configuration
    migration_scope: list[MigrationScopeItem] | None = None
    starting_balance: bool = False
    source_date: date | None = None

    # MCP connection details (api key is intentionally excluded from responses)
    mcp_server_url: str | None = None

    # Project status
    status: str
    current_step: int = 0
    created_by: uuid.UUID
    created_by_name: str | None = None
    updated_by: uuid.UUID | None = None
    updated_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    effective_permission: str | None = None

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
