from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.erp.dependencies import get_erp_service
from src.modules.erp.service import ERPConfigService
from src.modules.mappings.matching import MatchingEngine
from src.modules.mappings.repository import MappingRepository
from src.modules.mappings.service import MappingService
from src.modules.projects.repository import ProjectRepository


def get_mapping_service(db: AsyncSession = Depends(get_db)) -> MappingService:
    return MappingService(
        mapping_repo=MappingRepository(db),
        project_repo=ProjectRepository(db),
        session=db,
    )


def get_matching_engine(erp_service: ERPConfigService = Depends(get_erp_service)) -> MatchingEngine:
    return MatchingEngine(erp_service=erp_service)
