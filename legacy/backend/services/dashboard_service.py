"""Dashboard service for companies and projects overview."""
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.user_repository import UserRepository
from repositories.company_repository import CompanyRepository
from repositories.project_repository import ProjectRepository
from repositories.project_access_repository import ProjectAccessRepository
from repositories.mapping_repository import MappingRepository


class DashboardService:
    """Service for dashboard-related operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.user_repo = UserRepository(db)
        self.company_repo = CompanyRepository(db)
        self.project_repo = ProjectRepository(db)
        self.access_repo = ProjectAccessRepository(db)
        self.mapping_repo = MappingRepository(db)
    
    async def get_user_companies(
        self, 
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get companies and projects accessible to the user.
        
        Returns: {companies: list, total_projects: int}
        """
        # Get all project IDs the user has access to
        user_access_list = await self.access_repo.find_user_projects(user_id)
        user_permissions = {a["project_id"]: a["permission"] for a in user_access_list}
        user_project_ids = list(user_permissions.keys())
        
        if not user_project_ids:
            return {"companies": [], "total_projects": 0}
        
        # Get all accessible projects
        projects = await self.project_repo.find_by_ids(user_project_ids)
        
        # Group projects by company_id
        company_projects: Dict[str, List[Dict]] = {}
        for project in projects:
            company_id = project.get("company_id")
            if company_id not in company_projects:
                company_projects[company_id] = []
            
            # Enrich project with access info
            project_id = project["id"]
            
            # Get access list for this project
            access_list = await self.access_repo.find_project_access_list(project_id)
            enriched_access = []
            for access in access_list:
                user_info = await self.user_repo.find_by_user_id(access["user_id"])
                enriched_access.append({
                    "user_id": access["user_id"],
                    "user_name": user_info.get("name", access["user_id"]) if user_info else access["user_id"],
                    "permission": access["permission"],
                    "assigned_at": access.get("assigned_at")
                })
            
            # Get mapping count
            mapping_count = await self.mapping_repo.count_by_project(project_id)
            
            # Get last edited by name
            last_edited_by = project.get("last_edited_by")
            last_edited_by_name = last_edited_by
            if last_edited_by:
                editor = await self.user_repo.find_by_user_id(last_edited_by)
                if editor:
                    last_edited_by_name = editor.get("name", last_edited_by)
            
            company_projects[company_id].append({
                **project,
                "user_permission": user_permissions.get(project_id, "viewer"),
                "access_list": enriched_access,
                "mapping_count": mapping_count,
                "last_edited_by": last_edited_by_name
            })
        
        # Build companies list
        companies_with_projects = []
        for company_id, proj_list in company_projects.items():
            company = await self.company_repo.find_by_company_id(company_id)
            if company:
                # Sort projects by updated_at descending
                proj_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                companies_with_projects.append({
                    **company,
                    "projects": proj_list
                })
        
        return {
            "companies": companies_with_projects,
            "total_projects": len(user_project_ids)
        }
    
    async def get_project_detail(
        self,
        project_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed project information including mappings.
        
        Returns: Project with company, mappings, access list, stats
        Raises: PermissionError if no access
        """
        # Check project exists
        project = await self.project_repo.find_by_id(project_id)
        if not project:
            return None
        
        # Check user access
        user_access = await self.access_repo.find_user_access(user_id, project_id)
        if not user_access:
            raise PermissionError("Access denied")
        
        # Get company info
        company = await self.company_repo.find_by_company_id(project.get("company_id", ""))
        
        # Get mappings
        mappings = await self.mapping_repo.find_by_project(project_id)
        
        # Get access list with user details
        access_list_raw = await self.access_repo.find_project_access_list(project_id)
        access_list = []
        for access in access_list_raw:
            user_info = await self.user_repo.find_by_user_id(access["user_id"])
            access_list.append({
                "user_id": access["user_id"],
                "user_name": user_info.get("name", access["user_id"]) if user_info else access["user_id"],
                "permission": access["permission"],
                "assigned_at": access.get("assigned_at")
            })
        
        # Get last edited by name
        last_edited_by = project.get("last_edited_by")
        last_edited_by_name = last_edited_by
        if last_edited_by:
            editor = await self.user_repo.find_by_user_id(last_edited_by)
            if editor:
                last_edited_by_name = editor.get("name", last_edited_by)
        
        # Get created by name
        created_by = project.get("created_by")
        created_by_name = None
        if created_by:
            creator = await self.user_repo.find_by_user_id(created_by)
            if creator:
                created_by_name = creator.get("name", created_by)
            else:
                # Try by internal ID
                creator = await self.user_repo.find_by_id(created_by)
                if creator:
                    created_by_name = creator.get("name")
        
        # Get mapping stats
        mapping_stats = await self.mapping_repo.get_mapping_stats(project_id)
        
        return {
            **project,
            "company": company or {},
            "user_permission": user_access["permission"],
            "access_list": access_list,
            "mappings": mappings,
            "mapping_count": len(mappings),
            "last_edited_by": last_edited_by_name,
            "created_by_name": created_by_name,
            "mapping_stats": mapping_stats
        }
