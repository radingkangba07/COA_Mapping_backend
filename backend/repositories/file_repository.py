"""File repository for file metadata storage."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class FileRepository(BaseRepository):
    """Repository for file metadata operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "files")
    
    async def find_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Find file by ID."""
        return await self.find_one({"id": file_id})
    
    async def find_by_storage_path(
        self, 
        storage_path: str
    ) -> Optional[Dict[str, Any]]:
        """Find file by storage path."""
        return await self.find_one({"storage_path": storage_path})
    
    async def find_by_project(
        self,
        project_id: str,
        file_type: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Find all files for a project."""
        query = {"project_id": project_id}
        
        if file_type:
            query["file_type"] = file_type
        
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}
        
        return await self.find_many(
            query, 
            sort=[("created_at", -1)]
        )
    
    async def create_file(
        self,
        project_id: str,
        original_filename: str,
        storage_path: str,
        file_type: str = "upload",
        content_type: str = "application/octet-stream",
        size_bytes: int = 0,
        company_id: Optional[str] = None,
        job_id: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        etag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a file metadata record."""
        now = datetime.now(timezone.utc).isoformat()
        file_record = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "project_id": project_id,
            "job_id": job_id,
            "file_type": file_type,
            "original_filename": original_filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
            "etag": etag,
            "status": "uploaded",
            "is_deleted": False,
            "uploaded_by": uploaded_by,
            "created_at": now,
            "updated_at": now
        }
        return await self.insert_one(file_record)
    
    async def soft_delete(
        self,
        file_id: str,
        deleted_by: Optional[str] = None
    ) -> bool:
        """Soft delete a file (mark as deleted)."""
        now = datetime.now(timezone.utc).isoformat()
        return await self.update_one(
            {"id": file_id},
            {
                "is_deleted": True,
                "deleted_at": now,
                "deleted_by": deleted_by
            }
        )
    
    async def hard_delete(self, file_id: str) -> bool:
        """Permanently delete file record."""
        return await self.delete_one({"id": file_id})
    
    async def update_status(
        self,
        file_id: str,
        status: str
    ) -> bool:
        """Update file status."""
        return await self.update_one(
            {"id": file_id},
            {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def delete_project_files(
        self, 
        project_id: str,
        soft: bool = True
    ) -> int:
        """Delete all files for a project."""
        if soft:
            now = datetime.now(timezone.utc).isoformat()
            result = await self.collection.update_many(
                {"project_id": project_id},
                {"$set": {"is_deleted": True, "deleted_at": now}}
            )
            return result.modified_count
        return await self.delete_many({"project_id": project_id})
