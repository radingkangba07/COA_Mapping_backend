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
