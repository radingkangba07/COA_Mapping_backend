from coa_db_models.auth.models import User
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError, UnauthorizedError
from src.modules.auth.email_service import EmailService
from src.modules.auth.invitation_service import InvitationService
from src.modules.auth.repository import (
    InvitationRepository,
    OrganizationRepository,
    RefreshTokenRepository,
    UserRepository,
)
from src.modules.auth.service import AuthService, ClientOrgService


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        session=db,
        org_repo=OrganizationRepository(db),
        email_service=EmailService(),
        refresh_token_repo=RefreshTokenRepository(db),
    )


def get_invitation_service(db: AsyncSession = Depends(get_db)) -> InvitationService:
    return InvitationService(
        invitation_repo=InvitationRepository(db),
        org_repo=OrganizationRepository(db),
        user_repo=UserRepository(db),
        session=db,
        email_service=EmailService(),
    )


def get_client_org_service(db: AsyncSession = Depends(get_db)) -> ClientOrgService:
    return ClientOrgService(
        org_repo=OrganizationRepository(db),
        session=db,
    )


async def get_current_user(
    authorization: str | None = Header(None),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if not authorization:
        raise UnauthorizedError("Authorization header is required")
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("Invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    return await service.get_current_user(token)
