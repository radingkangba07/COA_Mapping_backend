import logging
from typing import Literal
from uuid import UUID

from coa_db_models.auth.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from src.core.exceptions import AppError, ConflictError
from src.modules.auth.dependencies import get_current_user
from src.modules.item_profile.dependencies import (
    get_decision_repo,
    get_field_repo,
    get_item_profile_service,
    get_run_repo,
)
from src.modules.item_profile.repository import (
    ItemFieldProfileRepository,
    ItemProfileDecisionRepository,
    ItemProfileRunRepository,
)
from src.modules.item_profile.schemas import (
    CoverageMetrics,
    DecisionCreateRequest,
    DecisionResponse,
    ExecuteResponse,
    FieldDetailResponse,
    FieldListItem,
    PagedFieldsResponse,
    ProjectDecisionsResponse,
    RunCreateRequest,
    RunCreateResponse,
    RunDetailResponse,
    RunListItem,
)
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


@router.get(
    "/projects/{project_id}/item-profile/runs",
    response_model=list[RunListItem],
)
async def list_item_profile_runs(
    project_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
):
    runs = await run_repo.list_runs(project_id)
    return [
        RunListItem(
            run_id=r.id,
            status=r.status,
            row_count=r.source_row_count,
            field_count=r.field_count,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get(
    "/projects/{project_id}/item-profile/runs/{run_id}",
    response_model=RunDetailResponse,
)
async def get_item_profile_run(
    project_id: UUID,
    run_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    field_repo: ItemFieldProfileRepository = Depends(get_field_repo),
):
    run = await run_repo.get_run_or_404(run_id)
    coverage_data = await field_repo.compute_coverage(run_id)
    return RunDetailResponse(
        run_id=run.id,
        status=run.status,
        row_count=run.source_row_count,
        field_count=run.field_count,
        migration_key_field=run.migration_key_field,
        coverage=CoverageMetrics(**coverage_data),
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get(
    "/projects/{project_id}/item-profile/runs/{run_id}/fields",
    response_model=PagedFieldsResponse,
)
async def list_item_profile_fields(
    project_id: UUID,
    run_id: UUID,
    role: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: Literal["field_name", "null_pct", "uniqueness_pct"] = Query(default="field_name"),
    order: Literal["asc", "desc"] = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    field_repo: ItemFieldProfileRepository = Depends(get_field_repo),
):
    run = await run_repo.get_run_or_404(run_id)
    if run.status != "profiling_complete":
        raise ConflictError(f"Run {run_id} is not complete (status: {run.status})")

    fields, total = await field_repo.list_fields(
        run_id,
        role=role,
        severity=severity,
        search=search,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    items = [
        FieldListItem(
            field_name=f.field_name,
            detected_type=f.detected_type,
            severity=f.severity,
            cardinality=f.cardinality,
            semantic_role=f.semantic_role,
            confidence_score=f.confidence_score,
            null_pct=f.stats.get("null_pct") if f.stats else None,
            uniqueness_pct=f.stats.get("uniqueness_pct") if f.stats else None,
            anomaly_count=f.anomaly_count,
        )
        for f in fields
    ]
    return PagedFieldsResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/projects/{project_id}/item-profile/runs/{run_id}/fields/{field_name}",
    response_model=FieldDetailResponse,
)
async def get_item_profile_field(
    project_id: UUID,
    run_id: UUID,
    field_name: str,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    field_repo: ItemFieldProfileRepository = Depends(get_field_repo),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
):
    run = await run_repo.get_run_or_404(run_id)
    if run.status != "profiling_complete":
        raise ConflictError(f"Run {run_id} is not complete (status: {run.status})")

    fp = await field_repo.get_field_or_404(run_id, field_name)
    pending = await decision_repo.get_pending(run_id, field_name)
    current_decision = (
        DecisionResponse(
            decision_id=pending.id,
            field_name=pending.field_name,
            decision_type=pending.action,
            fix_type=pending.fix_type,
            fix_params=pending.transformation_config,
            status=pending.status,
            decided_at=pending.created_at,
        )
        if pending
        else None
    )
    return FieldDetailResponse(
        field_name=fp.field_name,
        detected_type=fp.detected_type,
        total_count=fp.total_count,
        null_count=fp.null_count,
        distinct_count=fp.distinct_count,
        severity=fp.severity,
        cardinality=fp.cardinality,
        semantic_role=fp.semantic_role,
        confidence_score=fp.confidence_score,
        evidence=fp.evidence,
        pattern_summary=fp.pattern_summary,
        anomaly_count=fp.anomaly_count,
        anomaly_examples=fp.anomaly_examples,
        stats=fp.stats,
        sample_values=fp.sample_values,
        current_decision=current_decision,
    )


# ---------------------------------------------------------------------------
# DAB-38 — Decision endpoints
# ---------------------------------------------------------------------------

def _decision_response(d) -> DecisionResponse:
    return DecisionResponse(
        decision_id=d.id,
        field_name=d.field_name,
        decision_type=d.action,
        fix_type=d.fix_type,
        fix_params=d.transformation_config,
        status=d.status,
        decided_at=d.created_at,
    )


@router.post(
    "/projects/{project_id}/item-profile/runs/{run_id}/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_decision(
    project_id: UUID,
    run_id: UUID,
    data: DecisionCreateRequest,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
):
    await run_repo.get_run_or_404(run_id)
    decision = await decision_repo.create_decision(
        run_id=run_id,
        field_name=data.field_name,
        decision_type=data.decision_type,
        fix_type=data.fix_type,
        fix_params=data.fix_params,
        user_id=user.id,
    )
    await decision_repo.session.commit()
    return _decision_response(decision)


@router.get(
    "/projects/{project_id}/item-profile/runs/{run_id}/decisions",
    response_model=list[DecisionResponse],
)
async def list_decisions(
    project_id: UUID,
    run_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
):
    await run_repo.get_run_or_404(run_id)
    decisions = await decision_repo.list_decisions(run_id)
    return [_decision_response(d) for d in decisions]


@router.delete(
    "/projects/{project_id}/item-profile/runs/{run_id}/decisions/{decision_id}",
    response_model=DecisionResponse,
)
async def undo_decision(
    project_id: UUID,
    run_id: UUID,
    decision_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
    field_repo: ItemFieldProfileRepository = Depends(get_field_repo),
):
    decision = await decision_repo.undo_decision(decision_id, user.id, field_repo=field_repo)
    await decision_repo.session.commit()
    return _decision_response(decision)


@router.post(
    "/projects/{project_id}/item-profile/runs/{run_id}/decisions/{decision_id}/execute",
    response_model=ExecuteResponse,
)
async def execute_decision(
    project_id: UUID,
    run_id: UUID,
    decision_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("editor")),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
    run_repo: ItemProfileRunRepository = Depends(get_run_repo),
    field_repo: ItemFieldProfileRepository = Depends(get_field_repo),
):
    decision = await decision_repo.get_decision_or_404(decision_id)

    if decision.action == "confirm_identifier":
        decision = await decision_repo.execute_confirm_identifier(
            decision_id, user.id, run_repo
        )
        await decision_repo.session.commit()
        return ExecuteResponse(
            decision_id=decision.id,
            field_name=decision.field_name,
            fix_type=None,
            status=decision.status,
            rows_affected=0,
        )

    if decision.fix_type == "custom":
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail="custom fix type is not yet implemented")

    try:
        decision, rows_affected = await decision_repo.execute_fix(
            decision_id, user.id, field_repo
        )
    except AppError:
        raise
    except NotImplementedError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=501, detail=str(exc))

    await decision_repo.session.commit()
    return ExecuteResponse(
        decision_id=decision.id,
        field_name=decision.field_name,
        fix_type=decision.fix_type,
        status=decision.status,
        rows_affected=rows_affected,
    )


@router.get(
    "/projects/{project_id}/profile-decisions",
    response_model=ProjectDecisionsResponse,
)
async def get_project_decisions(
    project_id: UUID,
    user: User = Depends(get_current_user),
    _access=Depends(require_project_access("viewer")),
    decision_repo: ItemProfileDecisionRepository = Depends(get_decision_repo),
):
    all_pending = await decision_repo.list_project_decisions(project_id)
    confirmed = [_decision_response(d) for d in all_pending if d.action == "confirm_identifier"]
    fixes = [_decision_response(d) for d in all_pending if d.action == "apply_fix"]
    return ProjectDecisionsResponse(confirmed_identifiers=confirmed, applied_fixes=fixes)
