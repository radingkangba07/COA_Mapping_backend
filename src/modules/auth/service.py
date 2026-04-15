import hashlib
import logging
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks

from src.core.config import get_settings
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.modules.auth.models import User
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
        return [{"id": member.org_id, "name": org_name, "role": member.role} for member, org_name in memberships]

    async def get_org_members(self, org_id, user: User) -> list[dict]:
        """Return members of an organization (caller must be a member)."""
        from uuid import UUID as _UUID

        if isinstance(org_id, str):
            org_id = _UUID(org_id)

        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")

        membership = await self.org_repo.get_member(org_id, user.id)
        if not membership:
            raise ForbiddenError("You are not a member of this organization")

        members = await self.org_repo.get_members_for_org(org_id)
        return [
            {
                "id": member.id,
                "user_id": member.user_id,
                "name": user_name,
                "email": user_email,
                "role": member.role,
                "joined_at": member.joined_at.isoformat(),
            }
            for member, user_name, user_email in members
        ]

    async def invite_to_org(self, org_id, email: str, role: str, user: User, background_tasks=None) -> dict:
        """Invite a user to an organization by email."""
        from uuid import UUID as _UUID

        if isinstance(org_id, str):
            org_id = _UUID(org_id)

        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")

        membership = await self.org_repo.get_member(org_id, user.id)
        if not membership:
            raise ForbiddenError("You are not a member of this organization")
        if membership.role not in ("owner", "admin"):
            raise ForbiddenError("Only owners and admins can invite members")

        # Check if already a member
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            existing_member = await self.org_repo.get_member(org_id, existing_user.id)
            if existing_member:
                raise ConflictError("User is already a member of this organization")

        # Check for existing pending invitation
        existing_invite = await self.org_repo.get_pending_invitation(org_id, email)
        if existing_invite:
            raise ConflictError("A pending invitation already exists for this email")

        # Create invitation token (7-day expiry)
        token = create_access_token(
            data={"sub": email, "org_id": str(org_id), "purpose": "org_invitation"},
            expires_delta=timedelta(days=7),
        )
        expires_at = datetime.now(UTC) + timedelta(days=7)

        invitation = await self.org_repo.create_invitation(
            org_id=org_id, email=email, role=role, token=token, invited_by=user.id, expires_at=expires_at
        )
        await self.session.commit()

        # Send invitation email in background
        if self.email_service and background_tasks:
            background_tasks.add_task(
                self.email_service.send_invite_email,
                to=email,
                inviter_name=user.name,
                org_name=org.name,
                token=token,
            )

        logger.info("Invitation sent to '%s' for org '%s' by user %s", email, org.name, user.id)
        return {
            "id": invitation.id,
            "email": invitation.email,
            "role": invitation.role,
            "status": invitation.status,
            "invited_at": invitation.invited_at.isoformat(),
        }

    async def get_org_invitations(self, org_id, user: User) -> list[dict]:
        """Return invitations for an organization (caller must be a member)."""
        from uuid import UUID as _UUID

        if isinstance(org_id, str):
            org_id = _UUID(org_id)

        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")

        membership = await self.org_repo.get_member(org_id, user.id)
        if not membership:
            raise ForbiddenError("You are not a member of this organization")

        invitations = await self.org_repo.get_invitations_for_org(org_id)
        return [
            {
                "id": inv.id,
                "email": inv.email,
                "role": inv.role,
                "status": inv.status,
                "invited_at": inv.invited_at.isoformat(),
            }
            for inv in invitations
        ]

    async def accept_invitation(self, token: str) -> dict:
        """Validate an org invitation token and add the user as a member."""
        try:
            payload = decode_token(token)
        except InvalidTokenError:
            logger.warning("Invitation acceptance failed: invalid or expired token")
            return {"success": False, "error": "Invalid or expired invitation link"}

        if payload.get("purpose") != "org_invitation":
            logger.warning("Invitation acceptance failed: wrong token purpose")
            return {"success": False, "error": "Invalid invitation link"}

        from uuid import UUID as _UUID

        email = payload.get("sub")
        org_id_str = payload.get("org_id")
        if not email or not org_id_str:
            logger.warning("Invitation acceptance failed: missing claims in token")
            return {"success": False, "error": "Invalid invitation link"}

        org_id = _UUID(org_id_str)

        invitation = await self.org_repo.get_invitation_by_token(token)
        if not invitation or invitation.status != "pending":
            logger.warning("Invitation acceptance failed: invitation not found or not pending for email '%s'", email)
            return {"success": False, "error": "Invitation not found or already used"}

        if invitation.expires_at < datetime.now(UTC):
            logger.warning("Invitation acceptance failed: invitation expired for email '%s'", email)
            return {"success": False, "error": "Invitation has expired"}

        user = await self.user_repo.get_by_email(email)
        if not user:
            logger.info("Invitation: no account for '%s', redirecting to signup", email)
            return {"success": True, "action": "redirect_to_signup", "email": email, "token": token}

        existing_member = await self.org_repo.get_member(org_id, user.id)
        if existing_member:
            logger.warning("Invitation acceptance failed: user '%s' already a member of org %s", email, org_id)
            return {"success": False, "error": "You are already a member of this organization"}

        if not user.is_verified:
            await self.user_repo.verify_user(user.id)

        await self.org_repo.create_member(user_id=user.id, org_id=org_id, role=invitation.role)
        invitation.status = "accepted"
        await self.session.flush()

        await self.user_repo.update_last_login(user.id)
        access_token = create_access_token(data={"sub": str(user.id)})
        refresh_token = create_refresh_token(data={"sub": str(user.id)})
        settings = get_settings()
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.refresh_token_repo.create(user_id=user.id, token_hash=token_hash, expires_at=expires_at)

        await self.session.commit()
        logger.info("User '%s' accepted invitation to org %s", email, org_id)
        return {
            "success": True,
            "action": "accepted",
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def cancel_invitation(self, org_id, invitation_id, user: User) -> dict:
        """Cancel (hard-delete) a pending org invitation."""
        from uuid import UUID as _UUID

        if isinstance(org_id, str):
            org_id = _UUID(org_id)
        if isinstance(invitation_id, str):
            invitation_id = _UUID(invitation_id)

        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")

        membership = await self.org_repo.get_member(org_id, user.id)
        if not membership:
            raise ForbiddenError("You are not a member of this organization")
        if membership.role not in ("owner", "admin"):
            raise ForbiddenError("Only owners and admins can cancel invitations")

        invitation = await self.org_repo.get_invitation_by_id(invitation_id)
        if not invitation or invitation.org_id != org_id:
            raise NotFoundError("Invitation not found")
        if invitation.status != "pending":
            raise ConflictError("Only pending invitations can be cancelled")

        await self.session.delete(invitation)
        await self.session.flush()
        await self.session.commit()
        logger.info("Invitation %s cancelled by user %s", invitation_id, user.id)
        return {"status": "cancelled"}

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
