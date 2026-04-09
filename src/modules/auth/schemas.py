import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    user_id: str


class UserResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    email: str
    name: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            is_active=user.is_active,
            last_login=user.last_login_at,
            created_at=user.created_at,
        )


class LoginResponse(BaseModel):
    success: bool = True
    user: UserResponse
    token: str
    is_new_user: bool


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    org_name: str


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    message: str
