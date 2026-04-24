import logging
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, Depends, status

from src.modules.auth.dependencies import get_current_user
from src.modules.mappings.account_types.dependencies import get_account_type_service
from src.modules.mappings.account_types.schemas import (
    AccountTypeMappingBulkSave,
    AccountTypeMappingBulkSaveResponse,
    AccountTypeMappingResponse,
    AccountTypeMappingUpdate,
)
from src.modules.mappings.account_types.service import AccountTypeMappingService
from src.modules.projects.dependencies import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mappings", tags=["account-type-mappings"])


@router.post(
    "/project/{project_id}/account-type-mappings",
    response_model=AccountTypeMappingBulkSaveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_save_account_type_mappings(
    project_id: UUID,
    data: AccountTypeMappingBulkSave,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    service: AccountTypeMappingService = Depends(get_account_type_service),
):
    try:
        return await service.bulk_save(project_id, data, user.id)
    except Exception:
        logger.exception("Failed to save account type mappings for project %s", project_id)
        raise


@router.get(
    "/project/{project_id}/account-type-mappings",
    response_model=list[AccountTypeMappingResponse],
)
async def list_account_type_mappings(
    project_id: UUID,
    _access=Depends(require_project_access("viewer")),
    service: AccountTypeMappingService = Depends(get_account_type_service),
):
    try:
        return await service.list_mappings(project_id)
    except Exception:
        logger.exception("Failed to list account type mappings for project %s", project_id)
        raise


@router.patch(
    "/account-type-mappings/{mapping_id}",
    response_model=AccountTypeMappingResponse,
)
async def update_account_type_mapping(
    mapping_id: UUID,
    data: AccountTypeMappingUpdate,
    user: User = Depends(get_current_user),
    service: AccountTypeMappingService = Depends(get_account_type_service),
):
    try:
        return await service.update_mapping(mapping_id, data, user.id)
    except Exception:
        logger.exception("Failed to update account type mapping %s", mapping_id)
        raise


@router.delete(
    "/project/{project_id}/account-type-mappings",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account_type_mappings(
    project_id: UUID,
    _access=Depends(require_project_access("editor")),
    service: AccountTypeMappingService = Depends(get_account_type_service),
):
    try:
        await service.clear_mappings(project_id)
    except Exception:
        logger.exception("Failed to delete account type mappings for project %s", project_id)
        raise
