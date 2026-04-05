"""User schemas."""
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class UserLogin(BaseModel):
    """Schema for user login."""
    user_id: str = Field(..., min_length=1, max_length=100)


class UserCreate(BaseModel):
    """Schema for creating a user."""
    user_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)


class UserResponse(BaseModel):
    """Schema for user response."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: str
    name: str
    email: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class UserBrief(BaseModel):
    """Brief user info for listings."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: str
    name: str
