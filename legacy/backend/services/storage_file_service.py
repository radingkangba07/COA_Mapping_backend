"""Storage file service for file metadata management with object storage."""
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.file_repository import FileRepository
from repositories.project_access_repository import ProjectAccessRepository


class StorageFileService:
    """Service for file metadata and storage operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.file_repo = FileRepository(db)
        self.access_repo = ProjectAccessRepository(db)
    
    async def create_file_record(
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
        """
        Create a file metadata record in the database.
        
        Returns: File metadata dict
        """
        return await self.file_repo.create_file(
            project_id=project_id,
            original_filename=original_filename,
            storage_path=storage_path,
            file_type=file_type,
            content_type=content_type,
            size_bytes=size_bytes,
            company_id=company_id,
            job_id=job_id,
            uploaded_by=uploaded_by,
            etag=etag
        )
    
    async def get_file(
        self,
        file_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get file metadata with access check.
        
        Returns: File metadata or None
        Raises: PermissionError if no access
        """
        file_meta = await self.file_repo.find_by_id(file_id)
        if not file_meta:
            return None
        
        # Check project access
        project_id = file_meta.get("project_id")
        if project_id:
            access = await self.access_repo.find_user_access(user_id, project_id)
            if not access:
                raise PermissionError("Access denied")
        
        return file_meta
    
    async def list_project_files(
        self,
        project_id: str,
        user_id: str,
        file_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List files for a project.
        
        Returns: {project_id: str, files: list, total: int}
        Raises: PermissionError if no access
        """
        # Check access
        access = await self.access_repo.find_user_access(user_id, project_id)
        if not access:
            raise PermissionError("Access denied")
        
        files = await self.file_repo.find_by_project(
            project_id=project_id,
            file_type=file_type
        )
        
        return {
            "project_id": project_id,
            "files": files,
            "total": len(files)
        }
    
    async def delete_file(
        self,
        file_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Soft delete a file.
        
        Returns: {success: bool, message: str}
        Raises: PermissionError if insufficient permissions
        """
        file_meta = await self.file_repo.find_by_id(file_id)
        if not file_meta:
            return {"success": False, "message": "File not found"}
        
        # Check permission (editor or above)
        project_id = file_meta.get("project_id")
        if project_id:
            access = await self.access_repo.find_user_access(user_id, project_id)
            if not access or access["permission"] == "viewer":
                raise PermissionError("Insufficient permissions")
        
        # Soft delete
        await self.file_repo.soft_delete(file_id, user_id)
        
        return {"success": True, "message": "File deleted"}
    
    async def check_upload_permission(
        self,
        project_id: str,
        user_id: str
    ) -> bool:
        """Check if user can upload to project."""
        access = await self.access_repo.find_user_access(user_id, project_id)
        if not access:
            return False
        return access["permission"] != "viewer"
