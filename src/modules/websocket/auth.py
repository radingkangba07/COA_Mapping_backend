import logging
from uuid import UUID

from coa_db_models.auth.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import InvalidTokenError, decode_token
from src.modules.auth.repository import UserRepository
from src.modules.projects.repository import ProjectAccessRepository
from src.modules.projects.service import permission_level

logger = logging.getLogger(__name__)


class WSAuthError(Exception):
    """Auth error with a WebSocket close code (4401 unauthorized, 4403 forbidden)."""

    def __init__(self, code: int, reason: str):
        self.code = code
        self.reason = reason
        super().__init__(reason)


async def authenticate_ws(token: str | None, project_id: UUID, db: AsyncSession) -> User:
    """Validate JWT + project access. Raises WSAuthError on any failure."""
    if not token:
        raise WSAuthError(4401, "Missing token")

    try:
        payload = decode_token(token)
    except InvalidTokenError:
        logger.warning("WS auth failed: invalid token")
        raise WSAuthError(4401, "Invalid or expired token") from None

    if payload.get("type") != "access":
        logger.warning("WS auth failed: wrong token type")
        raise WSAuthError(4401, "Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise WSAuthError(4401, "Invalid token")

    user = await UserRepository(db).get_by_id(UUID(user_id))
    if not user or not user.is_active:
        logger.warning("WS auth failed: user %s not found or inactive", user_id)
        raise WSAuthError(4401, "User not found or inactive")

    access = await ProjectAccessRepository(db).get_user_permission(user.id, project_id)
    if not access or permission_level(access.permission) < permission_level("viewer"):
        logger.warning("WS auth failed: user %s has no access to project %s", user.id, project_id)
        raise WSAuthError(4403, "No access to project")

    return user
