"""Mapping repository for COA mapping data access."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class MappingRepository(BaseRepository):
    """Repository for COA mapping operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "mappings")
    
    async def find_by_id(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """Find mapping by ID."""
        return await self.find_one({"id": mapping_id})
    
    async def find_by_project(
        self, 
        project_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Find all mappings for a project, optionally filtered by status."""
        query = {"project_id": project_id}
        if status:
            query["status"] = status
        return await self.find_many(query)
    
    async def save_mappings(
        self,
        project_id: str,
        mappings: List[Dict[str, Any]]
    ) -> int:
        """Save mappings for a project (replaces existing)."""
        # Delete existing mappings
        await self.delete_many({"project_id": project_id})
        
        if not mappings:
            return 0
        
        # Ensure each mapping has required fields
        now = datetime.now(timezone.utc).isoformat()
        for mapping in mappings:
            if "id" not in mapping:
                mapping["id"] = f"m-{str(uuid.uuid4())[:8]}"
            mapping["project_id"] = project_id
            if "created_at" not in mapping:
                mapping["created_at"] = now
        
        # Insert new mappings
        await self.collection.insert_many(mappings)
        return len(mappings)
    
    async def update_mapping(
        self,
        mapping_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update a single mapping."""
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await self.update_one({"id": mapping_id}, updates)
    
    async def get_mapping_stats(
        self, 
        project_id: str
    ) -> Dict[str, int]:
        """Get mapping statistics for a project."""
        pipeline = [
            {"$match": {"project_id": project_id}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        
        stats = {"total": 0, "approved": 0, "suggested": 0, "rejected": 0, "modified": 0}
        
        async for doc in self.collection.aggregate(pipeline):
            status = doc["_id"]
            count = doc["count"]
            if status in stats:
                stats[status] = count
            stats["total"] += count
        
        return stats
    
    async def count_by_project(self, project_id: str) -> int:
        """Count mappings for a project."""
        return await self.count({"project_id": project_id})
    
    async def delete_project_mappings(self, project_id: str) -> int:
        """Delete all mappings for a project."""
        return await self.delete_many({"project_id": project_id})
