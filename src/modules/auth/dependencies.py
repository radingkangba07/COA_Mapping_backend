from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError
from src.modules.auth.email_service import EmailService
from src.modules.auth.models import User
from src.modules.auth.repository import OrganizationRepository, UserRepository
from src.modules.auth.service import AuthService


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        session=db,
        org_repo=OrganizationRepository(db),
        email_service=EmailService(),
    )


async def get_current_user(
    authorization: str = Header(...),
    service: AuthService = Depends(get_auth_service),
) -> User:
    if not authorization.startswith("Bearer "):
        raise ForbiddenError("Invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    return await service.get_current_user(token)
