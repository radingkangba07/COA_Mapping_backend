from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository
from src.modules.auth.models import Organization, OrganizationMember, RefreshToken, User


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_user_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, user_id: str, name: str, email: str) -> User:
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
        return result.scalar_one_or_none()

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

    async def get_by_name(self, name: str) -> Organization | None:
        result = await self.session.execute(select(Organization).where(Organization.name == name))
        return result.scalar_one_or_none()

    async def create(self, name: str) -> Organization:
        org = Organization(name=name)
        self.session.add(org)
        await self.session.flush()
        return org

    async def create_member(self, user_id: UUID, org_id: UUID, role: str) -> OrganizationMember:
        member = OrganizationMember(user_id=user_id, org_id=org_id, role=role)
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_memberships_for_user(self, user_id: UUID) -> list:
        result = await self.session.execute(
            select(OrganizationMember, Organization.name.label("org_name"))
            .join(Organization, OrganizationMember.org_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
        )
        return result.all()
