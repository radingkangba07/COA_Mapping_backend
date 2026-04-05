from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func

from src.core.base_repository import BaseRepository
from src.modules.auth.models import User


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
