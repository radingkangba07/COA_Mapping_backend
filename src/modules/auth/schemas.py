import uuid
from datetime import datetime
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


# --- Invitation schemas ---


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "member"


class InvitationResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    status: str
    invited_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class InvitationMessageResponse(BaseModel):
    invitation_id: uuid.UUID
    message: str


# --- Org member schemas ---


class OrgMemberResponse(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str
    joined_at: datetime


class UserOrgResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: Literal["member", "admin"] = "member"


class OrgInvitationResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    invited_at: str
