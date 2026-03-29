"""Project repository for project data access."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class ProjectRepository(BaseRepository):
    """Repository for project operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "projects")
    
    async def find_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Find project by project id."""
        return await self.find_one({"id": project_id})
    
    async def find_by_company(self, company_id: str) -> List[Dict[str, Any]]:
        """Find all projects for a company."""
        return await self.find_many(
            {"company_id": company_id},
            sort=[("updated_at", -1)]
        )
    
    async def find_by_ids(self, project_ids: List[str]) -> List[Dict[str, Any]]:
        """Find projects by list of IDs."""
        return await self.find_many({"id": {"$in": project_ids}})
    
    async def create_project(
        self,
        name: str,
        source_erp: str = "",
        target_erp: str = "",
        company_id: str = "",
        created_by: str = "",
        description: Optional[str] = None,
        status: str = "draft",
        current_step: int = 0
    ) -> Dict[str, Any]:
        """Create a new project."""
        now = datetime.now(timezone.utc).isoformat()
        project = {
            "id": f"p-{str(uuid.uuid4())[:8]}",
            "company_id": company_id,
            "name": name,
            "source_erp": source_erp,
            "target_erp": target_erp,
            "status": status,
            "current_step": current_step,
            "description": description or "",
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
            "last_edited_by": created_by
        }
        return await self.insert_one(project)
    
    async def update_project(
        self,
        project_id: str,
        updates: Dict[str, Any],
        edited_by: Optional[str] = None
    ) -> bool:
        """Update project fields."""
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if edited_by:
            updates["last_edited_by"] = edited_by
        
        return await self.update_one({"id": project_id}, updates)
    
    async def update_status(
        self,
        project_id: str,
        status: str,
        edited_by: Optional[str] = None
    ) -> bool:
        """Update project status."""
        return await self.update_project(project_id, {"status": status}, edited_by)
    
    async def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        return await self.delete_one({"id": project_id})
