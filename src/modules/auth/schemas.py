import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    org_name: str


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    message: str


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class OrgMembership(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class MeResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    email: str
    is_verified: bool
    orgs: list[OrgMembership]


class OrgMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    joined_at: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["member", "admin"] = "member"


class OrgInvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    invited_at: str
