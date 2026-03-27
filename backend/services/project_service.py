"""Project service for project management operations."""
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.user_repository import UserRepository
from repositories.company_repository import CompanyRepository
from repositories.project_repository import ProjectRepository
from repositories.project_access_repository import ProjectAccessRepository
from repositories.mapping_repository import MappingRepository


class ProjectService:
    """Service for project operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)
        self.company_repo = CompanyRepository(db)
        self.project_repo = ProjectRepository(db)
        self.access_repo = ProjectAccessRepository(db)
        self.mapping_repo = MappingRepository(db)
    
    async def create_project(
        self,
        name: str,
        source_erp: str,
        target_erp: str,
        company_id: str,
        created_by: str,
        description: Optional[str] = None,
        company_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new project with initial access for creator.

        Returns: {success: bool, project: dict}
        """
        # Ensure company exists (create if not)
        await self.company_repo.get_or_create(company_id, name=company_name)
        
        # Create project
        project = await self.project_repo.create_project(
            name=name,
            source_erp=source_erp,
            target_erp=target_erp,
            company_id=company_id,
            created_by=created_by,
            description=description
        )
        
        # Grant admin access to creator
        await self.access_repo.grant_access(
            user_id=created_by,
            project_id=project["id"],
            permission="admin"
        )
        
        return {"success": True, "project": project}
    
    async def update_project(
        self,
        project_id: str,
        user_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update project fields.
        
        Returns: {success: bool, project: dict}
        Raises: PermissionError if insufficient permissions
        """
        # Check permission (editor or above)
        user_access = await self.access_repo.find_user_access(user_id, project_id)
        if not user_access or user_access["permission"] == "viewer":
            raise PermissionError("Insufficient permissions")
        
        # Filter allowed fields
        allowed_fields = ["name", "description", "status"]
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not filtered_updates:
            project = await self.project_repo.find_by_id(project_id)
            return {"success": True, "project": project}
        
        # Update
        await self.project_repo.update_project(project_id, filtered_updates, user_id)
        project = await self.project_repo.find_by_id(project_id)
        
        return {"success": True, "project": project}
    
    async def save_mappings(
        self,
        project_id: str,
        user_id: str,
        mappings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Save mappings for a project.
        
        Returns: {success: bool, mapping_count: int, saved_by: str}
        Raises: PermissionError if insufficient permissions
        """
        # Check permission
        user_access = await self.access_repo.find_user_access(user_id, project_id)
        if not user_access or user_access["permission"] == "viewer":
            raise PermissionError("Insufficient permissions")
        
        # Save mappings
        count = await self.mapping_repo.save_mappings(project_id, mappings)
        
        # Update project status to in_progress if draft
        project = await self.project_repo.find_by_id(project_id)
        if project and project.get("status") == "draft":
            await self.project_repo.update_status(project_id, "in_progress", user_id)
        else:
            # Just update the edited by info
            await self.project_repo.update_project(project_id, {}, user_id)
        
        # Get user name
        user = await self.user_repo.find_by_user_id(user_id)
        saved_by = user.get("name", user_id) if user else user_id
        
        return {
            "success": True,
            "mapping_count": count,
            "saved_by": saved_by
        }
    
    async def grant_access(
        self,
        project_id: str,
        requester_id: str,
        target_user_id: str,
        permission: str = "viewer"
    ) -> Dict[str, Any]:
        """
        Grant user access to a project.
        
        Returns: {success: bool, message: str}
        Raises: PermissionError if requester lacks admin rights
        """
        # Check requester has admin permission
        requester_access = await self.access_repo.find_user_access(requester_id, project_id)
        if not requester_access or requester_access["permission"] not in ["admin", "approver"]:
            raise PermissionError("Only admins can grant access")
        
        # Ensure target user exists (create if not)
        target_user_id = target_user_id.strip().lower()
        user = await self.user_repo.find_by_user_id(target_user_id)
        if not user:
            await self.user_repo.create_user(
                user_id=target_user_id,
                name=target_user_id.replace(".", " ").title()
            )
        
        # Grant access
        await self.access_repo.grant_access(
            user_id=target_user_id,
            project_id=project_id,
            permission=permission,
            assigned_by=requester_id
        )
        
        return {"success": True, "message": f"Access granted to {target_user_id}"}
    
    async def revoke_access(
        self,
        project_id: str,
        requester_id: str,
        target_user_id: str
    ) -> Dict[str, Any]:
        """
        Revoke user access from a project.
        
        Returns: {success: bool, message: str}
        Raises: PermissionError if requester lacks admin rights
        """
        # Check requester has admin permission
        requester_access = await self.access_repo.find_user_access(requester_id, project_id)
        if not requester_access or requester_access["permission"] not in ["admin", "approver"]:
            raise PermissionError("Only admins can revoke access")
        
        # Revoke access
        await self.access_repo.revoke_access(target_user_id, project_id)
        
        return {"success": True, "message": f"Access revoked from {target_user_id}"}
    
    async def check_user_access(
        self,
        project_id: str,
        user_id: str,
        required_permission: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if user has access to project.
        
        Returns: {has_access: bool, permission: str or None}
        """
        access = await self.access_repo.find_user_access(user_id, project_id)
        
        if not access:
            return {"has_access": False, "permission": None}
        
        permission = access["permission"]
        
        if required_permission:
            # Check if permission is sufficient
            permission_levels = {"viewer": 1, "editor": 2, "approver": 3, "admin": 4}
            required_level = permission_levels.get(required_permission, 0)
            user_level = permission_levels.get(permission, 0)
            
            return {
                "has_access": user_level >= required_level,
                "permission": permission
            }
        
        return {"has_access": True, "permission": permission}
