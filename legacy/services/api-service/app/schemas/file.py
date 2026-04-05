"""File schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class FileCreate(BaseModel):
    """Schema for creating a file record."""
    project_id: UUID
    file_type: str
    original_filename: str
    storage_path: Optional[str] = None
    columns: Optional[List[str]] = None
    row_count: int = 0


class FileResponse(BaseModel):
    """Schema for file response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    project_id: UUID
    file_type: str
    original_filename: str
    columns: Optional[Dict[str, Any]] = None
    row_count: int
    created_at: datetime


class FileUploadResponse(BaseModel):
    """Schema for file upload response."""
    file_id: UUID
    session_id: str  # Alias for project_id for backwards compatibility
    file_name: str
    columns: List[str]
    row_count: int
    sample_data: List[Dict[str, Any]]
