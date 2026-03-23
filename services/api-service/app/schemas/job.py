"""Job schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from app.models.job import JobStatus, JobType


class JobCreate(BaseModel):
    """Schema for creating a job."""
    project_id: UUID
    job_type: str = JobType.ACCOUNT_MATCHING.value
    input_data: Optional[Dict[str, Any]] = None


class JobResponse(BaseModel):
    """Schema for job response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    project_id: UUID
    job_type: str
    status: str
    progress: float
    message: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobStatusResponse(BaseModel):
    """Schema for job status polling response."""
    job_id: UUID
    status: str
    progress: float
    message: Optional[str] = None
    is_complete: bool = False
    has_error: bool = False
    result_available: bool = False


class JobResultResponse(BaseModel):
    """Schema for job result response."""
    job_id: UUID
    status: str
    result_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
