"""Fuzzy matching engine — pure logic, no DB. Ported from services/api-service/app/services/matching_service.py."""

from rapidfuzz import fuzz, process


class MatchingEngine:
    def __init__(self, erp_service=None):
        self.erp_service = erp_service

    def fuzzy_match_columns(
        self,
        source_columns: list[str],
        target_fields: list[dict],
        threshold: int = 60,
    ) -> list[dict]:
        mappings = []
        target_names = [f["name"] for f in target_fields]
        target_ids = [f["id"] for f in target_fields]

        for source_col in source_columns:
            name_match = process.extractOne(source_col, target_names, scorer=fuzz.WRatio, score_cutoff=threshold)
            id_match = process.extractOne(
                source_col.lower().replace(" ", "_"),
                target_ids,
                scorer=fuzz.WRatio,
                score_cutoff=threshold,
            )

            best_match = None
            best_score = 0
            match_type = "fuzzy"

            if name_match and (not id_match or name_match[1] >= id_match[1]):
                idx = target_names.index(name_match[0])
                best_match = target_ids[idx]
                best_score = name_match[1]
            elif id_match:
                best_match = id_match[0]
                best_score = id_match[1]

            # Check exact match (overrides fuzzy)
            source_normalized = source_col.lower().replace(" ", "_").replace("-", "_")
            for i, tid in enumerate(target_ids):
                if source_normalized == tid.lower() or source_col.lower() == target_names[i].lower():
                    best_match = tid
                    best_score = 100
                    match_type = "exact"
                    break

            if best_match:
                mappings.append(
                    {
                        "source_field": source_col,
                        "target_field": best_match,
                        "confidence": best_score,
                        "method": match_type,
                    }
                )
            else:
                mappings.append(
                    {
                        "source_field": source_col,
                        "target_field": "",
                        "confidence": 0,
                        "method": "unmatched",
                    }
                )

        return mappings

    def find_best_target_name(
        self,
        source_name: str,
        target_names: list[str],
        threshold: int = 50,
    ) -> tuple[str, float]:
        if not target_names or not source_name:
            return source_name, 0

        # Exact match first
        source_lower = source_name.lower().strip()
        for tn in target_names:
            if tn.lower().strip() == source_lower:
                return tn, 100

        # Fuzzy match
        match = process.extractOne(source_name, target_names, scorer=fuzz.WRatio, score_cutoff=threshold)
        if match:
            return match[0], match[1]

        return source_name, 0

    def create_hierarchical_mapping(
        self,
        source_data: list[dict],
        target_data: list[dict] | None,
        source_erp: str,
        target_erp: str,
    ) -> dict:
        # Get target account types from ERP service
        target_types: list[str] = []
        if self.erp_service:
            target_types = self.erp_service.get_account_types(target_erp)

        # Auto-detect columns from source data keys
        type_col = None
        name_col = None
        number_col = None

        if source_data:
            for col in source_data[0].keys():
                col_lower = col.lower()
                if ("type" in col_lower and "detail" not in col_lower) or col_lower == "type":
                    type_col = col
                if "name" in col_lower or "title" in col_lower:
                    name_col = col
                if "number" in col_lower or col_lower == "number" or ("account" in col_lower and "no" in col_lower):
                    number_col = col

        # Extract target account names
        target_names: list[str] = []
        if target_data:
            target_name_col = None
            for col in target_data[0].keys():
                col_lower = col.lower()
                if "name" in col_lower or "title" in col_lower:
                    target_name_col = col
                    break
            if target_name_col:
                target_names = [
                    str(row.get(target_name_col, "")).strip() for row in target_data if row.get(target_name_col)
                ]

        # Group by account type
        grouped: dict[str, dict] = {}
        for row in source_data:
            account_type = str(row.get(type_col, "Unknown")) if type_col else "Unknown"
            account_name = str(row.get(name_col, "")) if name_col else ""
            account_number = str(row.get(number_col, "")) if number_col else ""

            if account_type not in grouped:
                suggested_target = ""
                confidence = 0

                if target_types:
                    match = process.extractOne(account_type, target_types, scorer=fuzz.WRatio, score_cutoff=50)
                    if match:
                        suggested_target = match[0]
                        confidence = match[1]

                grouped[account_type] = {
                    "source_type": account_type,
                    "target_type": suggested_target,
                    "confidence": confidence,
                    "accounts": [],
                }

            best_target_name, name_confidence = self.find_best_target_name(account_name, target_names)

            grouped[account_type]["accounts"].append(
                {
                    "source_number": account_number,
                    "source_name": account_name,
                    "target_name": best_target_name,
                    "name_confidence": name_confidence,
                    "row_data": row,
                }
            )

        return {
            "type_column": type_col,
            "name_column": name_col,
            "number_column": number_col,
            "target_types": target_types,
            "grouped_mappings": list(grouped.values()),
            "total_accounts": sum(len(g["accounts"]) for g in grouped.values()),
            "total_types": len(grouped),
        }
