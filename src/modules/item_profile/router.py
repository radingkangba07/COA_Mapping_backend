import logging
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, status

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.item_profile.dependencies import get_item_profile_service
from src.modules.item_profile.schemas import RunCreateRequest, RunCreateResponse
from src.modules.item_profile.service import ItemProfileService
from src.modules.projects.dependencies import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["item-profile"])


@router.post(
    "/projects/{project_id}/item-profile/runs",
    response_model=RunCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_item_profile_run(
    project_id: UUID,
    data: RunCreateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    service: ItemProfileService = Depends(get_item_profile_service),
):
    try:
        result = await service.initiate_run(project_id, data.source_file_ref, user)
        background_tasks.add_task(
            service.process_run,
            result["run_id"],
            project_id,
            data.source_file_ref,
        )
        return RunCreateResponse(run_id=result["run_id"], status=result["status"])
    except AppError:
        raise
    except Exception:
        logger.exception("Unexpected error initiating item profile run for project %s", project_id)
        raise
