import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.modules.mappings.suggestions.dependencies import get_suggestion_service
from src.modules.mappings.suggestions.schemas import SuggestionListResponse
from src.modules.mappings.suggestions.service import SuggestionService
from src.modules.projects.dependencies import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mappings", tags=["suggestions"])


@router.get(
    "/project/{project_id}/suggestions",
    response_model=SuggestionListResponse,
)
async def list_suggestions(
    project_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    source_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _access=Depends(require_project_access("viewer")),
    service: SuggestionService = Depends(get_suggestion_service),
):
    try:
        return await service.list_suggestions_grouped(
            project_id, status=status_filter, source_type=source_type, skip=skip, limit=limit
        )
    except Exception:
        logger.exception("Failed to list suggestions for project %s", project_id)
        raise
