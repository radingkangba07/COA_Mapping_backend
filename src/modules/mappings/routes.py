import io
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.modules.mappings.dependencies import get_mapping_service, get_matching_engine
from src.modules.mappings.matching import MatchingEngine
from src.modules.mappings.schemas import (
    FuzzyMatchRequest,
    FuzzyMatchResponse,
    HierarchicalMappingRequest,
    HierarchicalMappingResponse,
    MappingBulkSaveResponse,
    MappingBulkUpdate,
    MappingCreate,
    MappingResponse,
    MappingStatsResponse,
    MappingUpdate,
)
from src.modules.mappings.service import MappingService
from src.modules.projects.dependencies import require_project_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mappings", tags=["mappings"])
legacy_mappings_router = APIRouter(prefix="/api/v1", tags=["mappings"], include_in_schema=False)


@router.post("/project/{project_id}", response_model=MappingBulkSaveResponse, status_code=status.HTTP_201_CREATED)
async def bulk_save_mappings(
    project_id: UUID,
    mappings: list[MappingCreate],
    _access=Depends(require_project_access("editor")),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        return await service.bulk_save(project_id, mappings)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to bulk save mappings for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to save mappings"})


@router.get("/project/{project_id}")
async def list_mappings(
    project_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    source_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    _access=Depends(require_project_access("viewer")),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        flat_mappings = await service.list_mappings(
            project_id, status=status_filter, source_type=source_type, skip=skip, limit=limit
        )

        # Group by (source_type, target_type) to match legacy response shape
        from collections import defaultdict

        groups: dict[tuple, list] = defaultdict(list)
        group_scores: dict[tuple, list] = defaultdict(list)

        for m in flat_mappings:
            key = (m.source_account_type or "", m.target_account_type or "")
            score = m.confidence_score
            groups[key].append({
                "source_number": m.source_account_number or "",
                "source_name": m.source_account_name,
                "target_name": m.target_account_name or "",
                "score": score,
                "remark": m.remark,
                "status": m.status,
            })
            group_scores[key].append(score)

        result = []
        for (source_type_val, target_type_val), accounts in groups.items():
            scores = group_scores[(source_type_val, target_type_val)]
            result.append({
                "source_type": source_type_val,
                "target_type": target_type_val,
                "confidence": round(sum(scores) / len(scores), 1) if scores else 0,
                "accounts": accounts,
            })

        return result
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list mappings for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list mappings"})


@router.patch("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: UUID,
    data: MappingUpdate,
    user: User = Depends(get_current_user),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        return await service.update_mapping(mapping_id, data)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to update mapping %s", mapping_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to update mapping"})


@router.post("/bulk-update")
async def bulk_update(
    data: MappingBulkUpdate,
    user: User = Depends(get_current_user),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        count = await service.bulk_update_status(data.mapping_ids, data.updates)
        return {"updated_count": count}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to bulk update mappings")
        return JSONResponse(status_code=500, content={"detail": "Failed to bulk update mappings"})


@router.patch("/bulk-status")
async def bulk_update_status_by_score(
    data: dict,
    user: User = Depends(get_current_user),
    service: MappingService = Depends(get_mapping_service),
):
    """Update mapping statuses by score range for a project (legacy endpoint)."""
    try:
        project_id = data.get("project_id")
        min_score = data.get("min_score", 0)
        max_score = data.get("max_score", 100)
        new_status = data.get("status", "confirmed")

        if not project_id:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="project_id is required")

        result = await service.bulk_update_by_score(
            project_id=UUID(project_id),
            min_score=min_score,
            max_score=max_score,
            new_status=new_status,
        )
        return result
    except (AppError, Exception) as exc:
        if isinstance(exc, AppError):
            raise
        logger.exception("Failed to bulk update by score")
        return JSONResponse(status_code=500, content={"detail": "Failed to bulk update by score"})


@router.post("/bulk", include_in_schema=False)
async def legacy_bulk_save(
    project_id: str = Query(...),
    mappings: list[dict] = [],  # noqa: B006
    user: User = Depends(get_current_user),
    service: MappingService = Depends(get_mapping_service),
):
    """Legacy /mappings/bulk endpoint — takes project_id as query param."""
    try:
        mapping_creates = [MappingCreate(**m) for m in mappings]
        return await service.bulk_save(UUID(project_id), mapping_creates)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to bulk save mappings (legacy) for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to save mappings"})


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: UUID,
    user: User = Depends(get_current_user),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        await service.delete_mapping(mapping_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to delete mapping %s", mapping_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to delete mapping"})


@router.get("/project/{project_id}/stats", response_model=MappingStatsResponse)
async def mapping_stats(
    project_id: UUID,
    _access=Depends(require_project_access("viewer")),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        return await service.get_stats(project_id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get mapping stats for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get mapping stats"})


@router.post("/project/{project_id}/export")
async def export_mappings(
    project_id: UUID,
    _access=Depends(require_project_access("viewer")),
    service: MappingService = Depends(get_mapping_service),
):
    try:
        excel_bytes = await service.export_to_excel(project_id)
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=mappings.xlsx"},
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to export mappings for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to export mappings"})


@router.post("/hierarchical", response_model=HierarchicalMappingResponse)
async def hierarchical_mapping(
    data: HierarchicalMappingRequest,
    user: User = Depends(get_current_user),
    engine: MatchingEngine = Depends(get_matching_engine),
):
    try:
        result = engine.create_hierarchical_mapping(
            source_data=data.source_data,
            target_data=data.target_data,
            source_system=data.source_system,
            target_system=data.target_system,
        )
        return result
    except Exception:
        logger.exception("Failed to create hierarchical mapping")
        return JSONResponse(status_code=500, content={"detail": "Failed to create hierarchical mapping"})


@router.post("/fuzzy-match", response_model=FuzzyMatchResponse)
async def fuzzy_match(
    data: FuzzyMatchRequest,
    user: User = Depends(get_current_user),
    engine: MatchingEngine = Depends(get_matching_engine),
):
    try:
        target_fields: list[dict] = []
        if engine.erp_service:
            system = engine.erp_service.get_system(data.target_system)
            if system:
                target_fields = system.get("fields", [])

        mappings = engine.fuzzy_match_columns(data.source_columns, target_fields, data.threshold)
        return FuzzyMatchResponse(mappings=mappings, target_fields=target_fields)
    except Exception:
        logger.exception("Failed to fuzzy match columns")
        return JSONResponse(status_code=500, content={"detail": "Failed to fuzzy match columns"})


# TODO: Remove legacy alias routes once frontend is updated to use /api/v1/mappings/* paths


@legacy_mappings_router.post("/fuzzy-match")
async def legacy_fuzzy_match(
    data: FuzzyMatchRequest,
    user: User = Depends(get_current_user),
    engine: MatchingEngine = Depends(get_matching_engine),
):
    return await fuzzy_match(data, user, engine)


@legacy_mappings_router.post("/hierarchical-mapping")
async def legacy_hierarchical_mapping(
    data: HierarchicalMappingRequest,
    user: User = Depends(get_current_user),
    engine: MatchingEngine = Depends(get_matching_engine),
):
    return await hierarchical_mapping(data, user, engine)
