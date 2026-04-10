import logging
from datetime import timedelta

from fastapi import BackgroundTasks

from src.core.exceptions import ConflictError, ForbiddenError
from src.core.security import InvalidTokenError, create_access_token, decode_token
from src.modules.auth.models import User
from src.modules.auth.protocols import OrganizationRepositoryProtocol, UserRepositoryProtocol
from src.modules.auth.schemas import LoginResponse, UserResponse

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepositoryProtocol,
        session=None,
        org_repo: OrganizationRepositoryProtocol | None = None,
        email_service=None,
    ):
        self.user_repo = user_repo
        self.session = session
        self.org_repo = org_repo
        self.email_service = email_service

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

    async def register(self, name: str, email: str, org_name: str, background_tasks: BackgroundTasks | None = None) -> dict:
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
        verification_token = create_access_token(
            data={"sub": str(user.id), "purpose": "email_verification"},
            expires_delta=timedelta(minutes=15),
        )

        # Store token for single-use validation
        await self.user_repo.set_verification_token(user.id, verification_token)

        await self.session.commit()

        # Send verification email in background after commit (so user exists in DB)
        if self.email_service and background_tasks:
            background_tasks.add_task(
                self.email_service.send_verification_email,
                to=email,
                name=name,
                token=verification_token,
            )

        logger.info("User registered: email='%s', org='%s'", email, org_name)
        return {"user_id": user.id, "message": "Verification email sent"}

    async def verify_email(self, token: str) -> dict:
        """Validate verification token, mark user as verified."""
        try:
            payload = decode_token(token)
        except InvalidTokenError:
            logger.warning("Verification failed: invalid or expired token")
            return {"success": False, "error": "Invalid or expired verification link"}

        if payload.get("purpose") != "email_verification":
            logger.warning("Verification failed: wrong token purpose")
            return {"success": False, "error": "Invalid verification link"}

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("Verification failed: no sub in token")
            return {"success": False, "error": "Invalid verification link"}

        # Check token matches stored token (single-use enforcement)
        user = await self.user_repo.get_by_verification_token(token)
        if not user or str(user.id) != user_id:
            logger.warning("Verification failed: token already used or mismatched for user %s", user_id)
            return {"success": False, "error": "Verification link already used or invalid"}

        if user.is_verified:
            return {"success": True, "message": "Email already verified"}

        await self.user_repo.verify_user(user.id)
        await self.session.commit()
        logger.info("User %s verified their email", user_id)
        return {"success": True, "message": "Email verified successfully"}

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
