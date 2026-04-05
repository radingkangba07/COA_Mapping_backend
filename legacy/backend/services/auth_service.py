"""Authentication service for user login and session management."""
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.user_repository import UserRepository


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)
    
    async def login(self, user_id: str) -> Dict[str, Any]:
        """
        Login with user ID (mock authentication).
        Auto-creates user if not exists.
        
        Returns: {success: bool, user: dict, token: str, is_new_user: bool}
        """
        user_id = user_id.strip().lower()
        
        # Check if user exists
        user = await self.user_repo.find_by_user_id(user_id)
        
        if user:
            # Update last login
            await self.user_repo.update_last_login(user_id)
            return {
                "success": True,
                "user": user,
                "token": f"mock-token-{user_id}",
                "is_new_user": False
            }
        
        # Auto-create new user (for demo purposes)
        name = user_id.replace(".", " ").title()
        new_user = await self.user_repo.create_user(
            user_id=user_id,
            name=name
        )
        
        return {
            "success": True,
            "user": new_user,
            "token": f"mock-token-{user_id}",
            "is_new_user": True
        }
    
    async def get_current_user(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get current user from token.
        
        Returns: User dict or None if invalid
        """
        if not token:
            return None
        
        # Remove Bearer prefix if present
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Extract user_id from mock token
        if token.startswith("mock-token-"):
            user_id = token.replace("mock-token-", "")
            return await self.user_repo.find_by_user_id(user_id)
        
        return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by user_id."""
        return await self.user_repo.find_by_user_id(user_id)
    
    async def get_user_by_internal_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get user by internal id (u-xxxx format)."""
        return await self.user_repo.find_by_id(id)
    
    def extract_user_id_from_token(self, authorization: str) -> Optional[str]:
        """Extract user_id from authorization header."""
        if not authorization:
            return None
        
        token = authorization.replace("Bearer ", "")
        if token.startswith("mock-token-"):
            return token.replace("mock-token-", "")
        return None
