import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class RunCreateRequest(BaseModel):
    source_file_ref: str

    @field_validator("source_file_ref")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_file_ref must not be empty")
        return v


class RunCreateResponse(BaseModel):
    run_id: uuid.UUID
    status: str


class RunListItem(BaseModel):
    run_id: uuid.UUID
    status: str
    row_count: int | None
    field_count: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class CoverageMetrics(BaseModel):
    completeness_pct: float | None
    uniqueness_pct: float | None
    pattern_conformance_pct: float | None


class RunDetailResponse(BaseModel):
    run_id: uuid.UUID
    status: str
    row_count: int | None
    field_count: int | None
    migration_key_field: str | None = None
    coverage: CoverageMetrics
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class FieldListItem(BaseModel):
    field_name: str
    detected_type: str
    severity: str | None
    cardinality: str | None
    semantic_role: str | None
    confidence_score: float | None
    null_pct: float | None
    uniqueness_pct: float | None
    anomaly_count: int | None

    model_config = {"from_attributes": True}


class PagedFieldsResponse(BaseModel):
    items: list[FieldListItem]
    total: int
    page: int
    page_size: int


class FieldDetailResponse(BaseModel):
    field_name: str
    detected_type: str
    total_count: int
    null_count: int
    distinct_count: int
    severity: str | None
    cardinality: str | None
    semantic_role: str | None
    confidence_score: float | None
    evidence: str | None
    pattern_summary: dict[str, Any] | None
    anomaly_count: int | None
    anomaly_examples: list[str] | None
    stats: dict[str, Any] | None
    sample_values: dict[str, Any] | None
    current_decision: "DecisionResponse | None" = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DAB-38 — Decision schemas
# ---------------------------------------------------------------------------

_DECISION_TYPES = Literal["confirm_identifier", "apply_fix", "ignore_field"]
_FIX_TYPES = Literal["uom_alias_normalise", "trim_whitespace", "standardise_case"]


class DecisionCreateRequest(BaseModel):
    field_name: str
    decision_type: _DECISION_TYPES
    fix_type: _FIX_TYPES | None = None
    fix_params: dict[str, Any] | None = None


class DecisionResponse(BaseModel):
    decision_id: uuid.UUID
    field_name: str
    decision_type: str
    fix_type: str | None
    fix_params: dict[str, Any] | None
    status: str
    decided_at: datetime

    model_config = {"from_attributes": True}


class ProjectDecisionsResponse(BaseModel):
    confirmed_identifiers: list[DecisionResponse]
    applied_fixes: list[DecisionResponse]


class ExecuteResponse(BaseModel):
    decision_id: uuid.UUID
    field_name: str
    fix_type: str | None
    status: str
    rows_affected: int
