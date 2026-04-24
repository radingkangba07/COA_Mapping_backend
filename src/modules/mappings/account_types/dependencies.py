from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.mappings.account_types.repository import AccountTypeMappingRepository
from src.modules.mappings.account_types.service import AccountTypeMappingService


def get_account_type_service(db: AsyncSession = Depends(get_db)) -> AccountTypeMappingService:
    return AccountTypeMappingService(
        repo=AccountTypeMappingRepository(db),
        session=db,
    )
