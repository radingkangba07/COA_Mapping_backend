from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository
from src.modules.auth.models import Organization, OrganizationMember, User


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
