import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from coa_db_models.auth.models import OrganizationInvitation, User
from fastapi import BackgroundTasks

from src.core.config import get_settings
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.security import InvalidTokenError, create_access_token, decode_token
from src.modules.auth.protocols import (
    InvitationRepositoryProtocol,
    OrganizationRepositoryProtocol,
    UserRepositoryProtocol,
)

logger = logging.getLogger(__name__)

INVITE_EXPIRY_DAYS = 7


class InvitationService:
    def __init__(
        self,
        invitation_repo: InvitationRepositoryProtocol,
        org_repo: OrganizationRepositoryProtocol,
        user_repo: UserRepositoryProtocol,
        session=None,
        email_service=None,
    ):
        self.invitation_repo = invitation_repo
        self.org_repo = org_repo
        self.user_repo = user_repo
        self.session = session
        self.email_service = email_service

    async def _require_owner(self, user_id: UUID, org_id: UUID) -> None:
        member = await self.org_repo.get_member(org_id, user_id)
        if not member or member.role != "owner":
            raise ForbiddenError("Only organization owners can perform this action")

    async def send_invitation(
        self,
        org_id: UUID,
        email: str,
        role: str,
        current_user: User,
        background_tasks: BackgroundTasks | None = None,
    ) -> OrganizationInvitation:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")

        await self._require_owner(current_user.id, org_id)

        existing = await self.invitation_repo.get_pending_by_email_and_org(email, org_id)
        if existing:
            raise ConflictError("A pending invitation already exists for this email")

        # Check if user is already a member
        existing_user = await self.user_repo.get_by_email(email)
        if existing_user:
            existing_member = await self.org_repo.get_member(org_id, existing_user.id)
            if existing_member:
                raise ConflictError("User is already a member of this organization")

        token = create_access_token(
            data={"sub": str(current_user.id), "org_id": str(org_id), "email": email, "purpose": "org_invite"},
            expires_delta=timedelta(days=INVITE_EXPIRY_DAYS),
        )
        expires_at = datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS)

        invitation = await self.invitation_repo.create_invitation(
            org_id=org_id,
            email=email,
            role=role,
            invited_by=current_user.id,
            token=token,
            expires_at=expires_at,
        )
        await self.session.commit()

        if self.email_service and background_tasks:
            background_tasks.add_task(
                self.email_service.send_invite_email,
                to=email,
                inviter_name=current_user.name,
                org_name=org.name,
                token=token,
            )

        logger.info("Invitation sent to '%s' for org %s by user %s", email, org_id, current_user.id)
        return invitation

    async def accept_invitation(self, token: str) -> dict:
        try:
            payload = decode_token(token)
        except InvalidTokenError:
            logger.warning("Invite acceptance failed: invalid or expired token")
            return {"success": False, "error": "Invalid or expired invitation link"}

        if payload.get("purpose") != "org_invite":
            logger.warning("Invite acceptance failed: wrong token purpose")
            return {"success": False, "error": "Invalid invitation link"}

        invitation = await self.invitation_repo.get_by_token(token)
        if not invitation:
            logger.warning("Invite acceptance failed: invitation not found")
            return {"success": False, "error": "Invitation not found or already used"}

        if invitation.status != "pending":
            return {"success": False, "error": "Invitation has already been used"}

        if invitation.expires_at < datetime.now(UTC):
            return {"success": False, "error": "Invitation has expired"}

        user = await self.user_repo.get_by_email(invitation.email)
        settings = get_settings()

        if user:
            # Auto-verify: accepting an invite link proves email ownership
            if not user.is_verified:
                await self.user_repo.verify_user(user.id)

            # Add to org
            existing_member = await self.org_repo.get_member(invitation.org_id, user.id)
            if not existing_member:
                await self.org_repo.create_member(
                    user_id=user.id,
                    org_id=invitation.org_id,
                    role=invitation.role,
                )
            await self.invitation_repo.mark_accepted(invitation.id)
            await self.session.commit()
            logger.info("User %s accepted invitation to org %s", user.id, invitation.org_id)
            return {
                "success": True,
                "action": "joined",
                "redirect_url": f"{settings.frontend_url}/dashboard",
            }

        # User doesn't exist — redirect to registration
        await self.session.commit()
        logger.info("Invite for '%s' redirecting to registration", invitation.email)
        return {
            "success": True,
            "action": "register",
            "redirect_url": f"{settings.frontend_url}/register?email={invitation.email}&invite_token={token}",
        }

    async def list_invitations(self, org_id: UUID, current_user: User) -> list[OrganizationInvitation]:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")
        await self._require_owner(current_user.id, org_id)
        return await self.invitation_repo.list_pending_by_org(org_id)

    async def cancel_invitation(self, org_id: UUID, invitation_id: UUID, current_user: User) -> None:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")
        await self._require_owner(current_user.id, org_id)
        await self.invitation_repo.delete_invitation(invitation_id)
        await self.session.commit()
        logger.info("Invitation %s cancelled by user %s", invitation_id, current_user.id)

    async def list_org_members(self, org_id: UUID, current_user: User) -> list[dict]:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")
        # Any org member can list members
        member = await self.org_repo.get_member(org_id, current_user.id)
        if not member:
            raise ForbiddenError("You are not a member of this organization")
        return await self.org_repo.list_members(org_id)

    async def remove_org_member(self, org_id: UUID, target_user_id: UUID, current_user: User) -> None:
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise NotFoundError("Organization not found")
        await self._require_owner(current_user.id, org_id)

        if target_user_id == current_user.id:
            raise ForbiddenError("Cannot remove yourself from the organization")

        target_member = await self.org_repo.get_member(target_user_id, org_id)
        if not target_member:
            raise NotFoundError("User is not a member of this organization")

        await self.org_repo.remove_member(target_user_id, org_id)
        await self.session.commit()
        logger.info("User %s removed from org %s by %s", target_user_id, org_id, current_user.id)

    async def list_user_orgs(self, current_user: User) -> list[dict]:
        memberships = await self.org_repo.get_memberships_for_user(current_user.id)
        return [{"id": member.org_id, "name": org_name, "role": member.role} for member, org_name in memberships]
