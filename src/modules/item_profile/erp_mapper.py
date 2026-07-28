from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_MAPS_PATH = Path(__file__).parent.parent.parent / "config" / "erp_field_maps.yaml"
_EAN_UPC_RE = re.compile(r"^0{12,13}$")


@lru_cache(maxsize=1)
def _load_all_maps() -> dict:
    with _MAPS_PATH.open() as f:
        return yaml.safe_load(f)


def reload_erp_maps() -> None:
    """Clear the map cache so the next call re-reads from disk."""
    _load_all_maps.cache_clear()


def _resolve_fields(target_system: str, all_maps: dict) -> list[dict] | None:
    """Return the field list for target_system, resolving 'extends' chains."""
    entry = all_maps.get(target_system)
    if entry is None:
        return None
    if "extends" in entry:
        return _resolve_fields(entry["extends"], all_maps)
    return entry.get("fields")


def _barcode_confirmed(erp_field: dict, pattern_summary: dict | None) -> bool:
    if not erp_field.get("barcode_validation") or not pattern_summary:
        return False
    dominant = pattern_summary.get("dominant") or ""
    return bool(_EAN_UPC_RE.match(dominant))


def classify_erp_target(
    target_system: str | None,
    semantic_role: str | None,
    detected_type: str | None,
    pattern_summary: dict | None = None,
) -> dict | None:
    """Return the best-fit target ERP field dict, or None when no map exists.

    Looks up target_system in erp_field_maps.yaml. Returns None for unknown
    ERPs so the field profile is still created — just without a mapping.

    Fit levels:
    - strong:  role matches AND type matches
    - partial: role matches XOR type matches
    """
    if not target_system:
        return None

    fields = _resolve_fields(target_system, _load_all_maps())
    if not fields:
        return None

    candidates: list[tuple[str, dict]] = []
    for erp_field in fields:
        role_match = semantic_role == erp_field["expected_role"]
        type_match = detected_type == erp_field["expected_type"]

        if role_match and type_match:
            fit = "strong"
        elif role_match or type_match:
            fit = "partial"
        else:
            continue

        candidates.append((fit, erp_field))

    if not candidates:
        return None

    def _rank(item: tuple[str, dict]) -> tuple[int, int]:
        fit, erp_field = item
        fit_score = 0 if fit == "strong" else 1
        barcode_score = 0 if _barcode_confirmed(erp_field, pattern_summary) else 1
        return (fit_score, barcode_score)

    candidates.sort(key=_rank)
    best_fit, best_field = candidates[0]

    notes = best_field.get("notes", "")
    if _barcode_confirmed(best_field, pattern_summary):
        dominant = (pattern_summary or {}).get("dominant") or ""
        suffix = "EAN-13" if len(dominant) == 13 else "UPC-A"
        notes = f"{notes} — {suffix} digit pattern confirmed"

    return {
        "field": best_field["name"],
        "label": best_field["label"],
        "fit": best_fit,
        "notes": notes,
    }
