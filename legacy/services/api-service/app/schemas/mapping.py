"""Mapping schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class MappingCreate(BaseModel):
    """Schema for creating a mapping."""
    project_id: UUID
    source_account_number: Optional[str] = None
    source_account_name: str
    source_account_type: Optional[str] = None
    target_account_number: Optional[str] = None
    target_account_name: Optional[str] = None
    target_account_type: Optional[str] = None
    confidence_score: float = 0.0
    status: str = "suggested"
    remark: str = "ai"
    source_row_data: Optional[Dict[str, Any]] = None


class MappingUpdate(BaseModel):
    """Schema for updating a mapping."""
    target_account_number: Optional[str] = None
    target_account_name: Optional[str] = None
    target_account_type: Optional[str] = None
    confidence_score: Optional[float] = None
    status: Optional[str] = None
    remark: Optional[str] = None
    notes: Optional[str] = None


class MappingResponse(BaseModel):
    """Schema for mapping response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    project_id: UUID
    source_account_number: Optional[str] = None
    source_account_name: str
    source_account_type: Optional[str] = None
    target_account_number: Optional[str] = None
    target_account_name: Optional[str] = None
    target_account_type: Optional[str] = None
    confidence_score: float
    status: str
    remark: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MappingBulkUpdate(BaseModel):
    """Schema for bulk updating mappings."""
    mapping_ids: List[UUID]
    updates: MappingUpdate


class AccountMapping(BaseModel):
    """Schema for account within a type group."""
    source_number: Optional[str] = None
    source_name: str
    target_name: Optional[str] = None
    name_confidence: float = 0.0
    user_changed: bool = False
    row_data: Optional[Dict[str, Any]] = None


class TypeGroupMapping(BaseModel):
    """Schema for grouped type mapping."""
    source_type: str
    target_type: Optional[str] = None
    confidence: float = 0.0
    accounts: List[AccountMapping]


class HierarchicalMappingRequest(BaseModel):
    """Schema for hierarchical mapping request."""
    source_data: List[Dict[str, Any]]
    target_data: Optional[List[Dict[str, Any]]] = None


class HierarchicalMappingResponse(BaseModel):
    """Schema for hierarchical mapping response."""
    type_column: Optional[str] = None
    name_column: Optional[str] = None
    number_column: Optional[str] = None
    target_types: List[str]
    grouped_mappings: List[TypeGroupMapping]
    total_accounts: int
    total_types: int
