from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "odoo_item_field_map.yaml"

_EAN_UPC_RE = re.compile(r"^0{12,13}$")


@lru_cache(maxsize=1)
def _load_odoo_map() -> list[dict]:
    with _YAML_PATH.open() as f:
        return yaml.safe_load(f)["fields"]


def reload_odoo_map() -> None:
    """Clear the YAML cache so the next call re-reads the file."""
    _load_odoo_map.cache_clear()


def _barcode_confirmed(odoo_field: dict, pattern_summary: dict | None) -> bool:
    if not odoo_field.get("barcode_validation") or not pattern_summary:
        return False
    dominant = pattern_summary.get("dominant") or ""
    return bool(_EAN_UPC_RE.match(dominant))


def classify_odoo_target(
    semantic_role: str | None,
    detected_type: str | None,
    pattern_summary: dict | None = None,
) -> dict | None:
    """Return the best-fit Odoo field dict or None if no match exists.

    Fit levels (Strong > Partial > no match):
    - Strong:  role matches AND type matches
    - Partial: role matches XOR type matches

    When multiple strong matches exist, a barcode-validation field with a
    confirmed EAN-13/UPC-A pattern takes priority.
    """
    candidates: list[tuple[str, dict]] = []

    for odoo_field in _load_odoo_map():
        role_match = semantic_role == odoo_field["expected_role"]
        type_match = detected_type == odoo_field["expected_type"]

        if role_match and type_match:
            fit = "strong"
        elif role_match or type_match:
            fit = "partial"
        else:
            continue

        candidates.append((fit, odoo_field))

    if not candidates:
        return None

    # Sort: strong > partial, then barcode-confirmed fields first within strong
    def _rank(item: tuple[str, dict]) -> tuple[int, int]:
        fit, field = item
        fit_score = 0 if fit == "strong" else 1
        barcode_score = 0 if _barcode_confirmed(field, pattern_summary) else 1
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
