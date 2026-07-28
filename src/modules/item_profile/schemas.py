import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

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
    fields_processed: int | None = None
    coverage: CoverageMetrics
    # Top stats bar
    duplicate_identifier_count: int | None = None
    invalid_uom_count: int | None = None
    missing_product_type_count: int | None = None
    fields_to_review_count: int | None = None
    # AI interpretation panel (populated by DAB-44)
    interpretation_text: str | None = None
    recommended_actions: list[dict] | None = None
    created_at: datetime
    completed_at: datetime | None
    estimated_completion: datetime | None = None

    model_config = {"from_attributes": True}


class FindingBadge(BaseModel):
    type: str
    label: str
    severity: str


class FieldListItem(BaseModel):
    field_name: str
    detected_type: str
    severity: str | None
    cardinality: str | None
    semantic_role: str | None
    confidence_score: float | None
    null_pct: float | None
    null_count: int | None
    total_count: int | None
    non_null_count: int | None
    distinct_count: int | None
    uniqueness_pct: float | None
    anomaly_count: int | None
    sample_values: list[str] | None
    findings: list[FindingBadge]
    migration_impact: str

    model_config = {"from_attributes": True}


class PagedFieldsResponse(BaseModel):
    items: list[FieldListItem]
    total: int
    page: int
    page_size: int


class FieldFindingSummary(BaseModel):
    all_fields: int
    blockers: int
    identifier_candidates: int
    duplicates: int
    missing_values: int
    invalid_values: int
    near_empty: int
    outliers: int
    value_list_detected: int
    reference_failures: int
    pattern_anomalies: int


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
    sample_values: list[str] | None
    findings: list[FindingBadge] = []
    erp_target: dict[str, Any] | None = None
    current_decision: "DecisionResponse | None" = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DAB-38 — Decision schemas
# ---------------------------------------------------------------------------

_DECISION_TYPES = Literal["confirm_identifier", "apply_fix", "ignore_field", "override_field_metadata"]
_FIX_TYPES = Literal["uom_alias_normalise", "trim_whitespace", "standardise_case", "custom"]

_VALID_DETECTED_TYPES = frozenset(["string", "integer", "decimal", "date", "boolean"])
_VALID_SEMANTIC_ROLES = frozenset([
    "identifier_candidate", "cross_subsidiary_identifier", "value_list",
    "free_text", "numeric_measure", "date_temporal", "ambiguous",
])


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


class FieldOverrideRequest(BaseModel):
    detected_type: str | None = None
    semantic_role: str | None = None

    @field_validator("detected_type")
    @classmethod
    def validate_detected_type(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_DETECTED_TYPES:
            raise ValueError(f"detected_type must be one of {sorted(_VALID_DETECTED_TYPES)}")
        return v

    @field_validator("semantic_role")
    @classmethod
    def validate_semantic_role(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_SEMANTIC_ROLES:
            raise ValueError(f"semantic_role must be one of {sorted(_VALID_SEMANTIC_ROLES)}")
        return v


class FieldOverrideResponse(BaseModel):
    field_name: str
    detected_type: str
    semantic_role: str | None
    erp_target: dict | None
