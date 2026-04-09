import logging
from datetime import timedelta

from src.core.exceptions import ConflictError, ForbiddenError
from src.core.security import create_access_token
from src.modules.auth.models import User
from src.modules.auth.protocols import OrganizationRepositoryProtocol, UserRepositoryProtocol
from src.modules.auth.schemas import LoginResponse, UserResponse

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self, user_repo: UserRepositoryProtocol, session=None, org_repo: OrganizationRepositoryProtocol | None = None
    ):
        self.user_repo = user_repo
        self.session = session
        self.org_repo = org_repo

    async def login(self, user_id: str) -> LoginResponse:
        """Login with user ID (mock authentication). Auto-creates user if not exists."""
        user_id = user_id.strip().lower()

        try:
            user = await self.user_repo.get_by_user_id(user_id)
            is_new_user = False

            if user:
                await self.user_repo.update_last_login(user.id)
                logger.info("User '%s' logged in", user_id)
            else:
                name = user_id.replace(".", " ").title()
                email = f"{user_id}@example.com"
                user = await self.user_repo.create(user_id=user_id, name=name, email=email)
                is_new_user = True
                logger.info("New user '%s' created and logged in", user_id)

            if self.session:
                await self.session.commit()
                await self.session.refresh(user)

            return LoginResponse(
                user=UserResponse.from_user(user),
                token=f"mock-token-{user_id}",
                is_new_user=is_new_user,
            )
        except Exception:
            logger.exception("Login failed for user_id='%s'", user_id)
            raise

    async def register(self, name: str, email: str, org_name: str) -> dict:
        """Register a new user with an organization."""
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            logger.warning("Registration failed: duplicate email '%s'", email)
            raise ConflictError("Email already registered")

        existing_org = await self.org_repo.get_by_name(org_name)
        if existing_org:
            logger.warning("Registration failed: duplicate org name '%s'", org_name)
            raise ConflictError("Organization name already taken")

        user = await self.user_repo.create(
            user_id=email.split("@")[0],
            email=email,
            name=name,
        )

        org = await self.org_repo.create(name=org_name)
        await self.org_repo.create_member(user_id=user.id, org_id=org.id, role="owner")

        # Generate verification token (JWT, 15min expiry)
        # TODO: Send verification email (SCRUM-16)
        create_access_token(
            data={"sub": str(user.id), "purpose": "email_verification"},
            expires_delta=timedelta(minutes=15),
        )

        await self.session.commit()

        logger.info("User registered: email='%s', org='%s'", email, org_name)
        return {"user_id": user.id, "message": "Verification email sent"}

    async def get_current_user(self, token: str) -> User:
        """Extract user from mock token."""
        if token.startswith("mock-token-"):
            user_id = token.removeprefix("mock-token-")
            try:
                user = await self.user_repo.get_by_user_id(user_id)
                if user and user.is_active:
                    return user
            except Exception:
                logger.exception("Error fetching user from token")
                raise

        logger.warning("Invalid token attempted")
        raise ForbiddenError("Invalid token")
