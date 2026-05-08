import hashlib
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import BackgroundTasks

from src.core.config import get_settings
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.modules.auth.protocols import (
    OrganizationRepositoryProtocol,
    RefreshTokenRepositoryProtocol,
    UserRepositoryProtocol,
)

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepositoryProtocol,
        org_repo: OrganizationRepositoryProtocol,
        refresh_token_repo: RefreshTokenRepositoryProtocol,
        session=None,
        email_service=None,
    ):
        self.user_repo = user_repo
        self.session = session
        self.org_repo = org_repo
        self.email_service = email_service
        self.refresh_token_repo = refresh_token_repo

    async def register(
        self,
        name: str,
        email: str,
        org_name: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict:
        """Register a new user with an organization."""
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            logger.warning("Registration failed: duplicate email '%s'", email)
            raise ConflictError("Email already registered")

        existing_org = await self.org_repo.get_by_name(org_name)
        if existing_org:
            logger.warning("Registration failed: duplicate org name '%s'", org_name)
            raise ConflictError("Organization name already taken")

        user = await self.user_repo.create_user(
            user_id=email,
            email=email,
            name=name,
        )

        org = await self.org_repo.create(name=org_name, org_type="employer")
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

    async def request_magic_link(self, email: str, background_tasks=None) -> dict:
        """Send magic link login email to verified user."""
        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.warning("Login failed: no account for email '%s'", email)
            raise NotFoundError("No account found with this email")
        if not user.is_verified:
            logger.warning("Login failed: unverified email '%s'", email)
            raise ForbiddenError("Please verify your email first")

        token = create_access_token(
            data={"sub": str(user.id), "purpose": "magic_link"},
            expires_delta=timedelta(minutes=15),
        )
        await self.user_repo.set_magic_link_token(user.id, token)
        await self.session.commit()

        if self.email_service and background_tasks:
            background_tasks.add_task(
                self.email_service.send_magic_link_email,
                to=email,
                name=user.name,
                token=token,
            )

        logger.info("Magic link sent to '%s'", email)
        return {"message": "Magic link sent to your email"}

    async def verify_magic_link(self, token: str) -> dict:
        """Verify magic link token and issue access + refresh tokens."""
        try:
            payload = decode_token(token)
        except InvalidTokenError:
            logger.warning("Magic link verification failed: invalid or expired token")
            return {"success": False, "error": "Invalid or expired magic link"}

        if payload.get("purpose") != "magic_link":
            logger.warning("Magic link verification failed: wrong token purpose")
            return {"success": False, "error": "Invalid magic link"}

        user = await self.user_repo.get_by_magic_link_token(token)
        if not user or str(user.id) != payload.get("sub"):
            logger.warning("Magic link verification failed: token already used or mismatched")
            return {"success": False, "error": "Magic link already used or invalid"}

        # Clear magic link token (single-use)
        await self.user_repo.clear_magic_link_token(user.id)
        await self.user_repo.update_last_login(user.id)

        # Generate access + refresh tokens
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

        # Store refresh token hash
        settings = get_settings()
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(user_id=user.id, token_hash=token_hash, expires_at=expires_at)

        await self.session.commit()
        logger.info("User %s logged in via magic link", user.id)

        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": str(user.id),
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        """Exchange refresh token for new token pair (rotation)."""
        try:
            payload = decode_token(refresh_token)
        except InvalidTokenError:
            logger.warning("Token refresh failed: invalid or expired refresh token")
            raise ForbiddenError("Invalid refresh token") from None

        if payload.get("type") != "refresh":
            logger.warning("Token refresh failed: wrong token type '%s'", payload.get("type"))
            raise ForbiddenError("Invalid refresh token")

        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        stored = await self.refresh_token_repo.get_by_token_hash(token_hash)
        if not stored:
            logger.warning("Token refresh failed: token revoked or not found for user %s", payload.get("sub"))
            raise ForbiddenError("Refresh token revoked or invalid")

        # Revoke old token
        await self.refresh_token_repo.revoke(token_hash)

        # Issue new pair
        settings = get_settings()
        user_id = payload["sub"]
        new_access = create_access_token(data={"sub": user_id})
        new_refresh = create_refresh_token(data={"sub": user_id})

        new_hash = hashlib.sha256(new_refresh.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(user_id=stored.user_id, token_hash=new_hash, expires_at=expires_at)

        await self.session.commit()
        logger.info("Tokens refreshed for user %s", user_id)

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def logout(self, refresh_token: str) -> dict:
        """Revoke refresh token."""
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        await self.refresh_token_repo.revoke(token_hash)
        await self.session.commit()
        logger.info("User logged out, refresh token revoked")
        return {"message": "Logged out"}

    async def get_current_user(self, token: str) -> User:
        """Extract user from JWT access token."""
        try:
            payload = decode_token(token)
        except InvalidTokenError:
            logger.warning("Auth failed: invalid or expired access token")
            raise ForbiddenError("Invalid or expired token") from None

        if payload.get("type") != "access":
            logger.warning("Auth failed: wrong token type '%s'", payload.get("type"))
            raise ForbiddenError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("Auth failed: no sub claim in token")
            raise ForbiddenError("Invalid token")

        from uuid import UUID

        user = await self.user_repo.get_by_id(UUID(user_id))
        if not user or not user.is_active:
            logger.warning("Auth failed: user %s not found or inactive", user_id)
            raise ForbiddenError("User not found or inactive")
        return user

    async def get_user_orgs(self, user: User) -> list[dict]:
        """Return the user's organization memberships."""
        memberships = await self.org_repo.get_memberships_for_user(user.id)
        return [
            {"id": member.org_id, "name": org_name, "role": member.role, "org_type": org_type}
            for member, org_name, org_type in memberships
        ]

    async def get_me(self, user: User) -> dict:
        """Return user profile with org memberships."""
        orgs = await self.get_user_orgs(user)
        return {
            "id": user.id,
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "is_verified": user.is_verified,
            "orgs": orgs,
        }


class ClientOrgService:
    def __init__(self, org_repo: OrganizationRepositoryProtocol, session=None):
        self.org_repo = org_repo
        self.session = session

    async def _require_employer_admin(self, user_id: UUID, employer_org_id: UUID) -> None:
        member = await self.org_repo.get_member(employer_org_id, user_id)
        if not member or member.role not in ("owner", "admin"):
            raise ForbiddenError("Only employer org admins can perform this action")

    async def create_client(self, employer_org_id: UUID, data, current_user: User):
        employer = await self.org_repo.get_by_id(employer_org_id)
        if not employer:
            raise NotFoundError("Organization not found")
        if employer.org_type != "employer":
            raise ForbiddenError("Cannot create a client under a client organization")
        await self._require_employer_admin(current_user.id, employer_org_id)

        client = await self.org_repo.create_client(
            name=data.name,
            parent_org_id=employer_org_id,
            description=data.description,
            slug=None,
        )
        await self.org_repo.create_member(user_id=current_user.id, org_id=client.id, role="owner")

        if self.session:
            await self.session.commit()
        logger.info("Client org '%s' created under %s by user %s", client.name, employer_org_id, current_user.id)
        return client

    async def list_clients(self, employer_org_id: UUID, current_user: User):
        employer = await self.org_repo.get_by_id(employer_org_id)
        if not employer:
            raise NotFoundError("Organization not found")
        member = await self.org_repo.get_member(employer_org_id, current_user.id)
        if not member:
            raise ForbiddenError("You are not a member of this organization")
        return await self.org_repo.list_clients(employer_org_id)

    async def get_client(self, employer_org_id: UUID, client_id: UUID, current_user: User):
        employer_member = await self.org_repo.get_member(employer_org_id, current_user.id)
        client_member = await self.org_repo.get_member(client_id, current_user.id)
        if not employer_member and not client_member:
            raise ForbiddenError("Access denied")
        client = await self.org_repo.get_client(client_id, employer_org_id)
        if not client:
            raise NotFoundError("Client organization not found")
        return client

    async def update_client(self, employer_org_id: UUID, client_id: UUID, data, current_user: User):
        client = await self.org_repo.get_client(client_id, employer_org_id)
        if not client:
            raise NotFoundError("Client organization not found")

        employer_member = await self.org_repo.get_member(employer_org_id, current_user.id)
        client_member = await self.org_repo.get_member(client_id, current_user.id)
        is_employer_admin = employer_member and employer_member.role in ("owner", "admin")
        is_client_admin = client_member and client_member.role in ("owner", "admin")
        if not is_employer_admin and not is_client_admin:
            raise ForbiddenError("Insufficient permissions to update this client organization")

        updated = await self.org_repo.update_org(
            org_id=client_id,
            name=data.name,
            description=data.description,
        )
        if self.session:
            await self.session.commit()
        logger.info("Client org %s updated by user %s", client_id, current_user.id)
        return updated
