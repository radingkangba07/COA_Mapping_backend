"""User repository for user data access."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    """Repository for user operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "users")
    
    async def find_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Find user by user_id (login identifier)."""
        return await self.find_one({"user_id": user_id})
    
    async def find_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Find user by internal id."""
        return await self.find_one({"id": id})
    
    async def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find user by email."""
        return await self.find_one({"email": email})
    
    async def create_user(
        self,
        user_id: str,
        name: str,
        email: Optional[str] = None,
        is_active: bool = True
    ) -> Dict[str, Any]:
        """Create a new user."""
        now = datetime.now(timezone.utc).isoformat()
        user = {
            "id": f"u-{str(uuid.uuid4())[:8]}",
            "user_id": user_id,
            "name": name,
            "email": email or f"{user_id}@example.com",
            "is_active": is_active,
            "created_at": now,
            "last_login": now
        }
        return await self.insert_one(user)
    
    async def update_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return await self.update_one(
            {"user_id": user_id},
            {"last_login": now}
        )
    
    async def get_all_active_users(self) -> list:
        """Get all active users."""
        return await self.find_many({"is_active": True})
