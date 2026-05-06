from datetime import UTC, datetime
from uuid import UUID

from coa_db_models.auth.models import Organization, OrganizationInvitation, OrganizationMember, RefreshToken, User
from sqlalchemy import delete, select
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_user_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(func.lower(User.email) == email.lower()))
        return result.scalar_one_or_none()

    async def create_user(self, user_id: str, name: str, email: str) -> User:
        user = User(user_id=user_id, email=email, name=name)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def update_last_login(self, user_id: UUID) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.last_login_at = func.now()
            await self.session.flush()

    async def set_verification_token(self, user_id: UUID, token: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.verification_token = token
            await self.session.flush()

    async def verify_user(self, user_id: UUID) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.is_verified = True
            user.verification_token = None
            await self.session.flush()

    async def get_by_verification_token(self, token: str) -> User | None:
        result = await self.session.execute(select(User).where(User.verification_token == token))
        return result.scalar_one_or_none()

    async def set_magic_link_token(self, user_id: UUID, token: str) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.magic_link_token = token
            await self.session.flush()

    async def get_by_magic_link_token(self, token: str) -> User | None:
        result = await self.session.execute(select(User).where(User.magic_link_token == token))
        return result.scalar_one_or_none()

    async def clear_magic_link_token(self, user_id: UUID) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.magic_link_token = None
            await self.session.flush()


class RefreshTokenRepository:
    def __init__(self, session):
        self.session = session

    async def create(self, user_id: UUID, token_hash: str, expires_at) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        )
        rt: RefreshToken | None = result.scalar_one_or_none()
        return rt

    async def revoke(self, token_hash: str) -> None:
        result = await self.session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        rt = result.scalar_one_or_none()
        if rt:
            rt.revoked_at = func.now()
            await self.session.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )
        for rt in result.scalars():
            rt.revoked_at = func.now()
        await self.session.flush()


class OrganizationRepository:
    def __init__(self, session):
        self.session = session

    async def get_by_id(self, org_id: UUID) -> Organization | None:
        return await self.session.get(Organization, org_id)

    async def get_by_name(self, name: str) -> Organization | None:
        result = await self.session.execute(select(Organization).where(Organization.name == name))
        org: Organization | None = result.scalar_one_or_none()
        return org

    async def create(self, name: str, slug: str | None = None, org_type: str = "employer") -> Organization:
        import re

        if not slug:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        org = Organization(name=name, slug=slug, org_type=org_type)
        self.session.add(org)
        await self.session.flush()
        return org

    async def create_client(
        self, name: str, parent_org_id: UUID, description: str | None = None, slug: str | None = None
    ) -> Organization:
        import re

        if not slug:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        org = Organization(
            name=name, slug=slug, org_type="client", parent_org_id=parent_org_id, description=description
        )
        self.session.add(org)
        await self.session.flush()
        await self.session.refresh(org)
        return org

    async def list_clients(self, parent_org_id: UUID) -> list[Organization]:
        result = await self.session.execute(
            select(Organization)
            .where(Organization.parent_org_id == parent_org_id, Organization.org_type == "client")
            .order_by(Organization.name)
        )
        return list(result.scalars().all())

    async def get_client(self, client_id: UUID, parent_org_id: UUID) -> Organization | None:
        result = await self.session.execute(
            select(Organization).where(
                Organization.id == client_id,
                Organization.parent_org_id == parent_org_id,
                Organization.org_type == "client",
            )
        )
        return result.scalar_one_or_none()

    async def update_org(
        self, org_id: UUID, name: str | None = None, description: str | None = None
    ) -> Organization | None:
        import re

        org = await self.session.get(Organization, org_id)
        if not org:
            return None
        if name is not None:
            org.name = name
            org.slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        if description is not None:
            org.description = description
        await self.session.flush()
        await self.session.refresh(org)
        return org


    async def create_member(self, user_id: UUID, org_id: UUID, role: str) -> OrganizationMember:
        member = OrganizationMember(user_id=user_id, org_id=org_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_member(self, org_id: UUID, user_id: UUID) -> OrganizationMember | None:
        result = await self.session.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.org_id == org_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_members(self, org_id: UUID) -> list[dict]:
        result = await self.session.execute(
            select(
                OrganizationMember.user_id,
                User.name,
                User.email,
                OrganizationMember.role,
                OrganizationMember.joined_at,
            )
            .join(User, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.org_id == org_id)
            .order_by(OrganizationMember.joined_at)
        )
        return [
            {
                "user_id": row.user_id,
                "name": row.name,
                "email": row.email,
                "role": row.role,
                "joined_at": row.joined_at,
            }
            for row in result.all()
        ]

    async def remove_member(self, user_id: UUID, org_id: UUID) -> None:
        await self.session.execute(
            delete(OrganizationMember).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.org_id == org_id,
            )
        )
        await self.session.flush()

    async def get_memberships_for_user(self, user_id: UUID) -> list:
        result = await self.session.execute(
            select(
                OrganizationMember,
                Organization.name.label("org_name"),
                Organization.org_type.label("org_type"),
            )
            .join(Organization, OrganizationMember.org_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
        )
        return list(result.all())

    async def get_members_for_org(self, org_id: UUID) -> list:
        result = await self.session.execute(
            select(OrganizationMember, User.name.label("user_name"), User.email.label("user_email"))
            .join(User, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.org_id == org_id)
            .order_by(OrganizationMember.joined_at)
        )
        return list(result.all())

    async def get_pending_invitation(self, org_id: UUID, email: str) -> OrganizationInvitation | None:
        result = await self.session.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.org_id == org_id,
                func.lower(OrganizationInvitation.email) == email.lower(),
                OrganizationInvitation.status == "pending",
            )
        )
        invitation: OrganizationInvitation | None = result.scalar_one_or_none()
        return invitation

    async def create_invitation(
        self, org_id: UUID, email: str, role: str, token: str, invited_by: UUID, expires_at
    ) -> OrganizationInvitation:
        invitation = OrganizationInvitation(
            org_id=org_id, email=email, role=role, token=token, invited_by=invited_by, expires_at=expires_at
        )
        self.session.add(invitation)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def get_invitations_for_org(self, org_id: UUID) -> list[OrganizationInvitation]:
        result = await self.session.execute(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.org_id == org_id)
            .order_by(OrganizationInvitation.invited_at.desc())
        )
        return list(result.scalars().all())

    async def get_invitation_by_token(self, token: str) -> OrganizationInvitation | None:
        result = await self.session.execute(select(OrganizationInvitation).where(OrganizationInvitation.token == token))
        invitation: OrganizationInvitation | None = result.scalar_one_or_none()
        return invitation

    async def get_invitation_by_id(self, invitation_id: UUID) -> OrganizationInvitation | None:
        result = await self.session.execute(
            select(OrganizationInvitation).where(OrganizationInvitation.id == invitation_id)
        )
        invitation: OrganizationInvitation | None = result.scalar_one_or_none()
        return invitation

    async def delete_invitation(self, invitation_id: UUID) -> None:
        result = await self.session.execute(
            select(OrganizationInvitation).where(OrganizationInvitation.id == invitation_id)
        )
        obj = result.scalar_one_or_none()
        if obj:
            await self.session.delete(obj)
            await self.session.flush()


class InvitationRepository:
    def __init__(self, session):
        self.session = session

    async def create_invitation(
        self, org_id: UUID, email: str, role: str, invited_by: UUID, token: str, expires_at: datetime
    ) -> OrganizationInvitation:
        invitation = OrganizationInvitation(
            org_id=org_id,
            email=email,
            role=role,
            invited_by=invited_by,
            token=token,
            expires_at=expires_at,
        )
        self.session.add(invitation)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def get_by_token(self, token: str) -> OrganizationInvitation | None:
        result = await self.session.execute(select(OrganizationInvitation).where(OrganizationInvitation.token == token))
        return result.scalar_one_or_none()

    async def get_pending_by_email_and_org(self, email: str, org_id: UUID) -> OrganizationInvitation | None:
        result = await self.session.execute(
            select(OrganizationInvitation).where(
                func.lower(OrganizationInvitation.email) == email.lower(),
                OrganizationInvitation.org_id == org_id,
                OrganizationInvitation.status == "pending",
                OrganizationInvitation.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_by_org(self, org_id: UUID) -> list[OrganizationInvitation]:
        result = await self.session.execute(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.org_id == org_id, OrganizationInvitation.status == "pending")
            .order_by(OrganizationInvitation.invited_at.desc())
        )
        return list(result.scalars().all())

    async def delete_invitation(self, invitation_id: UUID) -> None:
        invitation = await self.session.get(OrganizationInvitation, invitation_id)
        if invitation:
            await self.session.delete(invitation)
            await self.session.flush()

    async def mark_accepted(self, invitation_id: UUID) -> None:
        invitation = await self.session.get(OrganizationInvitation, invitation_id)
        if invitation:
            invitation.status = "accepted"
            await self.session.flush()
