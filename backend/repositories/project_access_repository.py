"""Project access repository for managing user-project permissions."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class ProjectAccessRepository(BaseRepository):
    """Repository for project access/permissions."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "project_access")
    
    async def find_user_access(
        self, 
        user_id: str, 
        project_id: str
    ) -> Optional[Dict[str, Any]]:
        """Find user's access to a specific project."""
        return await self.find_one({
            "user_id": user_id,
            "project_id": project_id
        })
    
    async def find_project_access_list(
        self, 
        project_id: str
    ) -> List[Dict[str, Any]]:
        """Get all access entries for a project."""
        return await self.find_many({"project_id": project_id})
    
    async def find_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all project access entries for a user."""
        return await self.find_many({"user_id": user_id})
    
    async def grant_access(
        self,
        user_id: str,
        project_id: str,
        permission: str = "viewer",
        assigned_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Grant user access to a project (upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        
        # Check if access already exists
        existing = await self.find_user_access(user_id, project_id)
        
        if existing:
            # Update existing permission
            await self.update_one(
                {"user_id": user_id, "project_id": project_id},
                {
                    "permission": permission,
                    "assigned_at": now,
                    "assigned_by": assigned_by
                }
            )
            return {**existing, "permission": permission, "assigned_at": now}
        
        # Create new access
        access = {
            "user_id": user_id,
            "project_id": project_id,
            "permission": permission,
            "assigned_at": now,
            "assigned_by": assigned_by
        }
        return await self.insert_one(access)
    
    async def revoke_access(
        self, 
        user_id: str, 
        project_id: str
    ) -> bool:
        """Remove user's access to a project."""
        return await self.delete_one({
            "user_id": user_id,
            "project_id": project_id
        })
    
    async def delete_project_access(self, project_id: str) -> int:
        """Delete all access entries for a project."""
        return await self.delete_many({"project_id": project_id})
    
    async def get_user_project_ids(self, user_id: str) -> List[str]:
        """Get list of project IDs the user has access to."""
        access_list = await self.find_user_projects(user_id)
        return [a["project_id"] for a in access_list]
    
    async def get_user_permissions_map(
        self, 
        user_id: str
    ) -> Dict[str, str]:
        """Get a mapping of project_id -> permission for a user."""
        access_list = await self.find_user_projects(user_id)
        return {a["project_id"]: a["permission"] for a in access_list}
