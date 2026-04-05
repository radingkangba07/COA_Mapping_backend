"""ERP system schemas."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ERPField(BaseModel):
    """Schema for ERP field definition."""
    id: str
    name: str
    type: str
    required: bool = False


class ERPSystem(BaseModel):
    """Schema for ERP system."""
    id: str
    name: str
    description: str
    fields: List[ERPField]


class FieldMapping(BaseModel):
    """Schema for field mapping result."""
    source_field: str
    target_field: str
    confidence: float
    method: str  # "exact", "fuzzy", "manual", "unmatched"


class FuzzyMatchRequest(BaseModel):
    """Schema for fuzzy match request."""
    source_columns: List[str]
    target_erp: str
    threshold: int = Field(default=60, ge=0, le=100)


class FuzzyMatchResponse(BaseModel):
    """Schema for fuzzy match response."""
    mappings: List[FieldMapping]
    target_fields: List[ERPField]
