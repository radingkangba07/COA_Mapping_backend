"""Company repository for company data access."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class CompanyRepository(BaseRepository):
    """Repository for company operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "companies")
    
    async def find_by_company_id(self, company_id: str) -> Optional[Dict[str, Any]]:
        """Find company by company_id."""
        return await self.find_one({"company_id": company_id})
    
    async def find_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Find company by internal id."""
        return await self.find_one({"id": id})
    
    async def create_company(
        self,
        company_id: str,
        name: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new company."""
        now = datetime.now(timezone.utc).isoformat()
        company = {
            "id": f"c-{str(uuid.uuid4())[:8]}",
            "company_id": company_id,
            "name": name,
            "description": description or "Auto-created company",
            "created_at": now
        }
        return await self.insert_one(company)
    
    async def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies."""
        return await self.find_many({})
    
    async def get_or_create(
        self,
        company_id: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing company or create a new one."""
        company = await self.find_by_company_id(company_id)
        if company:
            return company
        
        return await self.create_company(
            company_id=company_id,
            name=name or company_id.replace("-", " ").title()
        )
