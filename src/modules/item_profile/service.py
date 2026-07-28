import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pandas as pd
from coa_db_models.auth.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, PayloadTooLargeError, ValidationError
from src.modules.item_profile.publisher import ItemProfilePublisher
from src.modules.item_profile.repository import ItemProfileRunRepository
from src.modules.projects.dependencies import ensure_project_access
from src.modules.projects.repository import ProjectRepository
from src.modules.storage.s3_provider import S3Provider

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 500 * 1024 * 1024  # 500 MB
_TYPE_SAMPLE_ROWS = 500
_BOOL_STRINGS = {"true", "false", "1", "0", "yes", "no"}


def _infer_column_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "string"

    str_vals = non_null.astype(str)

    if all(v.lower() in _BOOL_STRINGS for v in str_vals):
        return "boolean"

    try:
        pd.to_numeric(non_null, errors="raise")
        as_float = non_null.astype(float)
        if (as_float == as_float.astype("int64")).all():
            int_vals = as_float.astype("int64")
            # Detect YYYYMMDD dates stored as integers (e.g. 20231215)
            if (
                len(int_vals) > 0
                and (int_vals >= 19000101).all()
                and (int_vals <= 20991231).all()
                and (int_vals % 10000 // 100).between(1, 12).all()
                and (int_vals % 100).between(1, 31).all()
            ):
                return "date"
            return "integer"
        return "decimal"
    except (ValueError, TypeError):
        pass

    parsed_dates = pd.to_datetime(non_null, errors="coerce", format="mixed")
    if parsed_dates.notna().all():
        return "date"

    return "string"


def _parse_csv(raw: bytes) -> pd.DataFrame:
    """Attempt UTF-8 (with BOM), then Latin-1. Raises ValidationError on failure."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding, nrows=_TYPE_SAMPLE_ROWS)
            if df.columns.empty:
                raise ValidationError("CSV has no header row or columns could not be detected")
            return df
        except ValidationError:
            raise
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise ValidationError(f"CSV parsing failed: {exc}") from exc

    raise ValidationError("CSV encoding could not be determined; expected UTF-8 or Latin-1")


def _count_rows(raw: bytes) -> int:
    """Count data rows (excluding header) without loading the full file into pandas."""
    if not raw:
        return 0
    line_count = raw.count(b"\n")
    if not raw.endswith(b"\n"):
        line_count += 1
    return max(0, line_count - 1)


# ---------------------------------------------------------------------------
# Field statistics engine (DAB-34)
# ---------------------------------------------------------------------------

_TOP_VALUES_LIMIT = 20


@dataclass
class FieldStats:
    field_name: str
    detected_type: str
    total_count: int
    null_count: int
    null_pct: float
    distinct_count: int
    non_null_count: int
    uniqueness_pct: float
    cardinality: str
    severity: str
    top_values: list[dict] = field(default_factory=list)
    text_len_min: int | None = None
    text_len_max: int | None = None
    text_len_mean: float | None = None
    numeric_min: float | None = None
    numeric_max: float | None = None
    numeric_mean: float | None = None
    numeric_std: float | None = None
    # DAB-35: pattern detection
    pattern_summary: dict | None = None
    anomaly_count: int = 0
    anomaly_examples: list[str] = field(default_factory=list)
    # DAB-36: semantic role
    semantic_role: str = "ambiguous"
    confidence_score: float = 0.0
    evidence: str = ""
    # Per-field duplicate metrics
    duplicate_row_count: int = 0
    duplicate_group_count: int = 0
    # Range anomaly (IQR outlier detection)
    outlier_count: int = 0
    outlier_examples: list[str] = field(default_factory=list)
    # Date format
    date_format: str | None = None  # 'yyyymmdd_int' | 'iso' | 'non_iso'
    date_format_consistency_pct: float | None = None


def _classify_cardinality(distinct_count: int) -> str:
    if distinct_count < 10:
        return "low"
    if distinct_count <= 100:
        return "medium"
    return "high"


def _assign_severity(null_pct: float) -> str:
    if null_pct > 50.0:
        return "blocker"
    if null_pct > 10.0:
        return "warning"
    return "ok"


def _top_values(series: pd.Series, total_rows: int) -> list[dict]:
    non_null = series.dropna()
    counts = non_null.astype(str).value_counts().head(_TOP_VALUES_LIMIT)
    return [
        {"value": v, "count": int(c), "pct": round(c / total_rows * 100, 2)}
        for v, c in counts.items()
    ]


# ---------------------------------------------------------------------------
# Pattern detection and anomaly engine (DAB-35)
# ---------------------------------------------------------------------------

_SUBSIDIARY_KEYWORDS = frozenset({"subsidiary", "company", "branch", "division"})
_ANOMALY_EXAMPLES_LIMIT = 10
_PATTERN_VARIANTS_LIMIT = 10
_DUPLICATE_EXAMPLES_LIMIT = 5


def _char_class_signature(value: str) -> str:
    """Convert each character to its class: alpha→A, digit→0, others retained."""
    out = []
    for ch in value:
        if ch.isalpha():
            out.append("A")
        elif ch.isdigit():
            out.append("0")
        else:
            out.append(ch)
    return "".join(out)


def _detect_pattern(non_null: pd.Series) -> dict | None:
    """Return pattern_summary dict for a non-null string series, or None if empty."""
    if non_null.empty:
        return None
    str_vals = non_null.astype(str)
    signatures = str_vals.apply(_char_class_signature)
    counts = signatures.value_counts()
    total = len(str_vals)
    dominant = counts.index[0]
    dominant_pct = round(int(counts.iloc[0]) / total * 100, 2)
    variants = [
        {"pattern": sig, "count": int(cnt), "pct": round(int(cnt) / total * 100, 2)}
        for sig, cnt in counts.iloc[1:].items()
    ][:_PATTERN_VARIANTS_LIMIT]
    return {"dominant": dominant, "dominant_pct": dominant_pct, "variants": variants}


def _detect_anomalies(non_null: pd.Series, dominant: str) -> tuple[int, list[str]]:
    """Return (anomaly_count, anomaly_examples) for values deviating from the dominant pattern."""
    str_vals = non_null.astype(str)
    mask = str_vals.apply(_char_class_signature) != dominant
    anomalous = str_vals[mask]
    return int(len(anomalous)), anomalous.tolist()[:_ANOMALY_EXAMPLES_LIMIT]


def detect_duplicates(df: pd.DataFrame, key_fields: list[str] | None = None) -> dict:
    """Identify rows sharing identical key field values. Defaults to all columns."""
    cols = key_fields if key_fields is not None else df.columns.tolist()
    cols = [c for c in cols if c in df.columns]
    if not cols:
        return {"group_count": 0, "total_duplicate_rows": 0, "examples": []}

    dupes = df[df.duplicated(subset=cols, keep=False)]
    if dupes.empty:
        return {"group_count": 0, "total_duplicate_rows": 0, "examples": []}

    groups = dupes.groupby(cols, dropna=False)
    examples = []
    for keys, grp in groups:
        if len(examples) >= _DUPLICATE_EXAMPLES_LIMIT:
            break
        key_vals = keys if isinstance(keys, tuple) else (keys,)
        examples.append({
            "key": {k: str(v) for k, v in zip(cols, key_vals)},
            "count": len(grp),
        })

    return {
        "group_count": groups.ngroups,
        "total_duplicate_rows": len(dupes),
        "examples": examples,
    }


def detect_cross_subsidiary_splits(
    df: pd.DataFrame,
    key_fields: list[str] | None = None,
) -> dict:
    """Detect key values that appear under multiple subsidiary/company column values."""
    subsidiary_col = next(
        (c for c in df.columns if any(kw in c.lower() for kw in _SUBSIDIARY_KEYWORDS)),
        None,
    )
    if subsidiary_col is None:
        return {"has_cross_subsidiary_splits": False, "split_count": 0, "examples": []}

    cols = key_fields if key_fields is not None else [c for c in df.columns if c != subsidiary_col]
    cols = [c for c in cols if c in df.columns and c != subsidiary_col]
    if not cols:
        return {"has_cross_subsidiary_splits": False, "split_count": 0, "examples": []}

    splits = df.groupby(cols, dropna=False)[subsidiary_col].nunique()
    split_keys = splits[splits > 1]
    split_count = int(len(split_keys))

    examples = []
    for keys in list(split_keys.index)[:_DUPLICATE_EXAMPLES_LIMIT]:
        key_vals = keys if isinstance(keys, tuple) else (keys,)
        mask = pd.Series(True, index=df.index)
        for col, val in zip(cols, key_vals):
            mask &= df[col] == val
        subs = df.loc[mask, subsidiary_col].unique().tolist()
        examples.append({
            "key": {c: str(v) for c, v in zip(cols, key_vals)},
            "subsidiaries": [str(s) for s in subs],
        })

    return {
        "has_cross_subsidiary_splits": split_count > 0,
        "split_count": split_count,
        "examples": examples,
    }


# ---------------------------------------------------------------------------
# Semantic role inference (DAB-36)
# ---------------------------------------------------------------------------

_ROLE_IDENTIFIER = "identifier_candidate"
_ROLE_CROSS_SUB = "cross_subsidiary_identifier"
_ROLE_VALUE_LIST = "value_list"
_ROLE_FREE_TEXT = "free_text"
_ROLE_NUMERIC = "numeric_measure"
_ROLE_DATE = "date_temporal"
_ROLE_AMBIGUOUS = "ambiguous"

_FREE_TEXT_MIN_LEN_MEAN = 40.0
_FREE_TEXT_MIN_UNIQUENESS = 80.0
_VALUE_LIST_MAX_DISTINCT = 20
_VALUE_LIST_MAX_NULL_PCT = 20.0


def infer_semantic_role(
    stats: "FieldStats",
    has_cross_subsidiary: bool,
    min_uniqueness: float,
    max_null_pct: float,
) -> tuple[str, float, str]:
    """Return (role, confidence, evidence) for a single field's stats."""
    base = (
        f"{stats.distinct_count:,} distinct values across {stats.non_null_count:,} "
        f"non-null records ({stats.uniqueness_pct}% unique)"
    )

    is_identifier = (
        stats.uniqueness_pct >= min_uniqueness
        and stats.null_pct < max_null_pct
        and stats.cardinality == "high"
    )

    if is_identifier and has_cross_subsidiary:
        return (
            _ROLE_CROSS_SUB,
            round(stats.uniqueness_pct / 100, 4),
            f"{base} — qualifies as Cross-Subsidiary Identifier "
            f"(≥{min_uniqueness}% unique, <{max_null_pct}% null, values span multiple subsidiaries)",
        )

    if is_identifier:
        return (
            _ROLE_IDENTIFIER,
            round(stats.uniqueness_pct / 100, 4),
            f"{base} — qualifies as Identifier Candidate "
            f"(≥{min_uniqueness}% unique, <{max_null_pct}% null)",
        )

    if stats.distinct_count <= _VALUE_LIST_MAX_DISTINCT and stats.null_pct < _VALUE_LIST_MAX_NULL_PCT:
        confidence = round(1 - (stats.distinct_count / _VALUE_LIST_MAX_DISTINCT), 4)
        return (
            _ROLE_VALUE_LIST,
            confidence,
            f"{base} — qualifies as Value List / Enumeration "
            f"(≤{_VALUE_LIST_MAX_DISTINCT} distinct values, <{_VALUE_LIST_MAX_NULL_PCT}% null)",
        )

    if (
        stats.detected_type == "string"
        and stats.text_len_mean is not None
        and stats.text_len_mean > _FREE_TEXT_MIN_LEN_MEAN
        and stats.uniqueness_pct > _FREE_TEXT_MIN_UNIQUENESS
    ):
        return (
            _ROLE_FREE_TEXT,
            0.7,
            f"{base} — qualifies as Free Text / Description "
            f"(mean length {stats.text_len_mean} chars, >{_FREE_TEXT_MIN_UNIQUENESS}% unique)",
        )

    if stats.detected_type in ("integer", "decimal"):
        return (
            _ROLE_NUMERIC,
            0.8,
            f"{base} — qualifies as Numeric Measure (inferred type: {stats.detected_type})",
        )

    if stats.detected_type == "date":
        return (
            _ROLE_DATE,
            0.9,
            f"{base} — qualifies as Date / Temporal (inferred type: date)",
        )

    return (
        _ROLE_AMBIGUOUS,
        0.0,
        f"{base} — no classification threshold met",
    )


def apply_semantic_roles(
    all_stats: list["FieldStats"],
    cross_sub_summary: dict,
    min_uniqueness: float,
    max_null_pct: float,
) -> list["FieldStats"]:
    """Assign semantic_role, confidence_score, and evidence to every FieldStats in place."""
    has_cross_sub = cross_sub_summary.get("has_cross_subsidiary_splits", False)
    for s in all_stats:
        s.semantic_role, s.confidence_score, s.evidence = infer_semantic_role(
            s, has_cross_sub, min_uniqueness, max_null_pct
        )
    return all_stats


def compute_field_stats(col_name: str, series: pd.Series) -> FieldStats:
    total_count = len(series)
    null_count = int(series.isna().sum())
    non_null_count = total_count - null_count
    null_pct = round(null_count / total_count * 100, 2) if total_count else 0.0

    non_null = series.dropna()
    distinct_count = int(non_null.nunique())
    uniqueness_pct = round(distinct_count / non_null_count * 100, 2) if non_null_count else 0.0

    detected_type = _infer_column_type(series)
    cardinality = _classify_cardinality(distinct_count)
    severity = _assign_severity(null_pct)
    top_vals = _top_values(series, total_count)

    text_len_min = text_len_max = text_len_mean = None
    numeric_min = numeric_max = numeric_mean = numeric_std = None
    pattern_summary: dict | None = None
    anomaly_count = 0
    anomaly_examples: list[str] = []

    duplicate_row_count = 0
    duplicate_group_count = 0
    if non_null_count > 0:
        str_non_null = non_null.astype(str)
        vc = str_non_null.value_counts()
        duplicate_row_count = int(str_non_null.duplicated(keep=False).sum())
        duplicate_group_count = int((vc > 1).sum())

    if detected_type == "string" and non_null_count > 0:
        lengths = non_null.astype(str).str.len()
        text_len_min = int(lengths.min())
        text_len_max = int(lengths.max())
        text_len_mean = round(float(lengths.mean()), 2)
        pattern_summary = _detect_pattern(non_null)
        if pattern_summary is not None:
            anomaly_count, anomaly_examples = _detect_anomalies(non_null, pattern_summary["dominant"])

    outlier_count = 0
    outlier_examples: list[str] = []
    date_format: str | None = None
    date_format_consistency_pct: float | None = None

    if detected_type in ("integer", "decimal") and non_null_count > 0:
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        if not numeric.empty:
            numeric_min = round(float(numeric.min()), 4)
            numeric_max = round(float(numeric.max()), 4)
            numeric_mean = round(float(numeric.mean()), 4)
            numeric_std = round(float(numeric.std()), 4) if len(numeric) > 1 else 0.0
            if len(numeric) >= 4:
                q1, q3 = float(numeric.quantile(0.25)), float(numeric.quantile(0.75))
                iqr = q3 - q1
                if iqr > 0:
                    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    mask = (numeric < lower) | (numeric > upper)
                    outlier_count = int(mask.sum())
                    if outlier_count > 0:
                        outlier_examples = numeric[mask].astype(str).head(5).tolist()

    if detected_type == "date" and non_null_count > 0:
        try:
            pd.to_numeric(non_null, errors="raise")
            date_format = "yyyymmdd_int"
            date_format_consistency_pct = 100.0
        except (ValueError, TypeError):
            str_vals = non_null.astype(str)
            iso_count = int(str_vals.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False).sum())
            date_format_consistency_pct = round(iso_count / non_null_count * 100, 2)
            date_format = "iso" if iso_count == non_null_count else "non_iso"

    return FieldStats(
        field_name=col_name,
        detected_type=detected_type,
        total_count=total_count,
        null_count=null_count,
        null_pct=null_pct,
        distinct_count=distinct_count,
        non_null_count=non_null_count,
        uniqueness_pct=uniqueness_pct,
        cardinality=cardinality,
        severity=severity,
        top_values=top_vals,
        text_len_min=text_len_min,
        text_len_max=text_len_max,
        text_len_mean=text_len_mean,
        numeric_min=numeric_min,
        numeric_max=numeric_max,
        numeric_mean=numeric_mean,
        numeric_std=numeric_std,
        pattern_summary=pattern_summary,
        anomaly_count=anomaly_count,
        anomaly_examples=anomaly_examples,
        duplicate_row_count=duplicate_row_count,
        duplicate_group_count=duplicate_group_count,
        outlier_count=outlier_count,
        outlier_examples=outlier_examples,
        date_format=date_format,
        date_format_consistency_pct=date_format_consistency_pct,
    )


def compute_all_stats(df: pd.DataFrame) -> list[FieldStats]:
    return [compute_field_stats(col, df[col]) for col in df.columns]


# ---------------------------------------------------------------------------
# Per-field findings and migration impact (source profile page)
# ---------------------------------------------------------------------------

def compute_field_findings(stats: "FieldStats") -> list[dict]:
    """Return an ordered list of finding badge dicts for one field."""
    findings: list[dict] = []

    # Completely empty column
    if stats.total_count > 0 and stats.null_count == stats.total_count:
        findings.append({"type": "all_null", "label": f"{stats.null_count} missing (100%)", "severity": "error"})
        return findings

    # Partial nulls
    if stats.null_count > 0:
        sev = "error" if stats.null_pct > 50 else "warning"
        findings.append({"type": "missing_values", "label": f"{stats.null_count} missing", "severity": sev})

    # Duplicate rows on identifier fields
    if (
        stats.duplicate_row_count > 0
        and stats.semantic_role in ("identifier_candidate", "cross_subsidiary_identifier")
    ):
        findings.append({"type": "duplicate_rows", "label": f"{stats.duplicate_row_count} duplicate rows", "severity": "error"})
        if stats.duplicate_group_count > 0:
            findings.append({"type": "duplicate_groups", "label": f"{stats.duplicate_group_count} groups", "severity": "warning"})

    # Pattern anomalies / invalid values
    if stats.anomaly_count > 0:
        if stats.semantic_role == "value_list":
            findings.append({"type": "invalid_values", "label": f"{stats.anomaly_count} invalid values", "severity": "error"})
        else:
            findings.append({"type": "pattern_anomaly", "label": f"{stats.anomaly_count} pattern anomalies", "severity": "warning"})

    # Range anomaly — IQR outliers on numeric fields
    outlier_count = getattr(stats, "outlier_count", 0) or 0
    if outlier_count > 0:
        findings.append({"type": "outliers", "label": f"{outlier_count} outliers", "severity": "warning"})
        findings.append({"type": "range_anomaly", "label": "Range anomaly", "severity": "warning"})

    # Non-ISO date format
    date_format = getattr(stats, "date_format", None)
    if date_format and date_format != "iso":
        findings.append({"type": "non_iso_format", "label": "Non-ISO format", "severity": "warning"})
        consistency = getattr(stats, "date_format_consistency_pct", None)
        if consistency is not None:
            findings.append({"type": "format_consistent", "label": f"{consistency}% format-consistent", "severity": "info"})

    # Value list / enumeration
    if stats.semantic_role == "value_list":
        findings.append({"type": "enumeration", "label": "Enumeration candidate", "severity": "info"})

    # Cross-subsidiary composite key
    if stats.semantic_role == "cross_subsidiary_identifier":
        findings.append({"type": "composite_key", "label": "Composite-key candidate", "severity": "info"})

    if not findings:
        findings.append({"type": "clean", "label": "No issues", "severity": "success"})

    return findings


def compute_migration_impact(stats: "FieldStats", findings: list[dict]) -> str:
    """Derive migration impact label from severity + findings."""
    finding_types = {f["type"] for f in findings}
    if "all_null" in finding_types or "duplicate_rows" in finding_types or stats.severity == "blocker":
        return "Blocker"
    if stats.severity == "warning" or "pattern_anomaly" in finding_types:
        return "Warning"
    if "missing_values" in finding_types:
        return "Review"
    return "Clean"


# ---------------------------------------------------------------------------
# Run-level domain stats (invalid UOM count, missing product type count)
# ---------------------------------------------------------------------------

_KNOWN_UOM_VALUES: frozenset[str] = frozenset({
    "nos", "no", "pcs", "pc", "each", "ea", "kg", "g", "mg",
    "l", "ml", "litre", "liter", "m", "cm", "mm", "mtrs", "mtr", "meter", "meters",
    "ft", "in", "inch", "unit", "units", "box", "set", "pair", "roll",
    "sheet", "pack", "lot", "bag", "bottle", "can", "drum", "tonne", "ton",
    "sqm", "sqft", "sqin", "lm", "rm",
})

_UOM_FIELD_KEYWORDS: tuple[str, ...] = ("unit", "uom", "measure", "uom_id")
_PRODUCT_TYPE_KEYWORDS: tuple[str, ...] = ("product type", "item type", "product_type", "item_type")


def detect_uom_issues(df: "pd.DataFrame", all_stats: "list[FieldStats]") -> int:
    """Count rows across UOM columns whose values are not in the known UOM vocabulary."""
    uom_fields = [
        s for s in all_stats
        if s.semantic_role == "value_list"
        and any(kw in s.field_name.lower() for kw in _UOM_FIELD_KEYWORDS)
    ]
    if not uom_fields:
        return 0
    total_invalid = 0
    for fs in uom_fields:
        if fs.field_name not in df.columns:
            continue
        col = df[fs.field_name].dropna().astype(str).str.strip().str.lower()
        total_invalid += int((~col.isin(_KNOWN_UOM_VALUES)).sum())
    return total_invalid


def detect_missing_product_type(df: "pd.DataFrame", all_stats: "list[FieldStats]") -> int:
    """Count null rows in the best candidate product-type column."""
    type_fields = [
        s for s in all_stats
        if any(kw in s.field_name.lower() for kw in _PRODUCT_TYPE_KEYWORDS)
    ]
    if not type_fields:
        return 0
    # Prefer the field with the fewest nulls (most informative)
    best = min(type_fields, key=lambda s: s.null_count)
    return best.null_count


def load_full_csv(raw: bytes) -> pd.DataFrame:
    """Parse the complete CSV (no row limit) for statistics computation."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            if df.columns.empty:
                raise RuntimeError("CSV has no detectable columns")
            return df
        except RuntimeError:
            raise
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise RuntimeError(f"CSV parsing failed: {exc}") from exc
    raise RuntimeError("CSV encoding could not be determined")


class ItemProfileService:
    def __init__(
        self,
        run_repo: ItemProfileRunRepository,
        store: S3Provider | None,
        publisher: ItemProfilePublisher | None,
        session: AsyncSession,
    ):
        self.run_repo = run_repo
        self.store = store
        self.publisher = publisher
        self.session = session

    async def initiate_run(self, project_id: UUID, source_file_ref: str, user: User) -> dict:
        """Validate inputs and create the run record synchronously. Returns {run_id, status}."""
        await ensure_project_access(self.session, user.id, project_id, "editor")

        project = await ProjectRepository(self.session).get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")

        if not self.store:
            raise ValidationError("Storage is not configured")

        if not self.store.object_exists(source_file_ref):
            raise ValidationError(f"File not found in storage: {source_file_ref}")

        size = self.store.get_object_size(source_file_ref)
        if size is not None and size > _MAX_FILE_BYTES:
            raise PayloadTooLargeError("File exceeds the 500 MB limit")

        run = await self.run_repo.create_run(
            project_id=project_id,
            started_at=datetime.now(UTC),
            source_file_ref=source_file_ref,
        )
        await self.session.commit()
        logger.info("Item profile run %s initiated for project %s", run.id, project_id)
        return {"run_id": run.id, "status": run.status}

    async def process_run(self, run_id: UUID, project_id: UUID, source_file_ref: str) -> None:
        """Background task: download, parse CSV, update run, publish NATS event."""
        try:
            assert self.store is not None
            raw, _ = self.store.get_object(source_file_ref)

            if len(raw) > _MAX_FILE_BYTES:
                raise PayloadTooLargeError("File exceeds the 500 MB limit")

            if len(raw) == 0:
                raise ValidationError("CSV file is empty")

            # Detect binary content — null bytes are present in all common binary formats
            # (PNG, PDF, XLSX, ZIP, etc.) but never in well-formed CSV text
            if b"\x00" in raw[:4096]:
                raise ValidationError("File does not appear to be a valid CSV (binary content detected)")

            sample_df = _parse_csv(raw)
            field_count = len(sample_df.columns)
            row_count = _count_rows(raw)

            await self.run_repo.update_run(
                run_id,
                status="profiling_pending",
                source_row_count=row_count,
                field_count=field_count,
                completed_at=datetime.now(UTC),
            )
            await self.session.commit()
            logger.info("Run %s ingested: %d rows, %d fields — status=profiling_pending", run_id, row_count, field_count)

            if self.publisher:
                await self.publisher.publish_run_created(run_id, project_id)

        except Exception as exc:
            error_msg = str(exc)
            logger.warning("Run %s ingestion failed: %s", run_id, error_msg)
            await self.run_repo.update_run(run_id, status="failed", error_detail=error_msg)
            await self.session.commit()
