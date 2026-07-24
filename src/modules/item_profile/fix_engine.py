"""Deterministic fix executor for item profile fields (DAB-39).

Operates on the top_values stored in item_field_profiles.stats so that
execution and undo are both possible without reloading the source CSV.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

_ALIASES_PATH = Path(__file__).parent / "odoo_uom_aliases.yaml"

_VALID_FIX_TYPES = frozenset(
    ["uom_alias_normalise", "trim_whitespace", "standardise_case", "custom"]
)
_VALID_CASE_VALUES = frozenset(["upper", "lower", "title"])


@lru_cache(maxsize=1)
def _load_uom_aliases() -> dict[str, str]:
    """Returns alias → canonical mapping, cached after first load."""
    with _ALIASES_PATH.open() as fh:
        data = yaml.safe_load(fh)
    result: dict[str, str] = {}
    for canonical, aliases in (data or {}).items():
        for alias in (aliases or []):
            result[str(alias)] = str(canonical)
    return result


def _build_transform(fix_type: str, fix_params: dict | None):
    """Return a value → value callable for the given fix type."""
    params = fix_params or {}
    if fix_type == "trim_whitespace":
        return lambda v: v.strip() if isinstance(v, str) else v
    if fix_type == "standardise_case":
        case = params.get("case", "lower")
        if case not in _VALID_CASE_VALUES:
            raise ValueError(f"fix_params.case must be one of {sorted(_VALID_CASE_VALUES)}")
        fn = {"upper": str.upper, "lower": str.lower, "title": str.title}[case]
        return lambda v: fn(v) if isinstance(v, str) else v
    if fix_type == "uom_alias_normalise":
        aliases = _load_uom_aliases()
        return lambda v: aliases.get(v, v) if isinstance(v, str) else v
    raise ValueError(f"Unknown fix_type: {fix_type!r}")


def apply_fix(
    top_values: list[dict],
    fix_type: str,
    fix_params: dict | None = None,
) -> tuple[list[dict], int, list[dict]]:
    """Apply a fix to a top_values list.

    Returns:
        new_top_values: merged and sorted value-count pairs after transformation.
        rows_affected:  count of rows whose value actually changed.
        change_log:     per-unique-value change records for the audit trail.
    """
    if fix_type == "custom":
        raise NotImplementedError("custom fix type is not yet implemented")

    transform = _build_transform(fix_type, fix_params)

    merged: dict[str, int] = defaultdict(int)
    rows_affected = 0
    change_log: list[dict] = []

    for entry in top_values:
        original = entry.get("value")
        count = int(entry.get("count", 0))
        transformed = transform(original) if original is not None else original

        if transformed != original:
            rows_affected += count
            change_log.append({"before": original, "after": transformed, "count": count})

        key = str(transformed) if transformed is not None else ""
        merged[key] += count

    new_top_values = [
        {"value": v, "count": c}
        for v, c in sorted(merged.items(), key=lambda x: -x[1])
    ]
    return new_top_values, rows_affected, change_log
