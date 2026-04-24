from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.mappings.suggestions.repository import SuggestionRepository
from src.modules.mappings.suggestions.service import SuggestionService


def get_suggestion_service(db: AsyncSession = Depends(get_db)) -> SuggestionService:
    return SuggestionService(
        repo=SuggestionRepository(db),
        session=db,
    )
