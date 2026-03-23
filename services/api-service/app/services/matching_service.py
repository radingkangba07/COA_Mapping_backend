"""Matching service for fuzzy matching logic."""
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import fuzz, process

from app.services.erp_service import erp_service


class MatchingService:
    """Service for fuzzy matching between source and target accounts.
    
    Note: This service contains the matching ALGORITHMS only.
    The actual heavy processing for large datasets should be handled
    by the ML service workers via the message queue.
    """
    
    def calculate_fuzzy_matches(
        self,
        source_columns: List[str],
        target_fields: List[Dict[str, Any]],
        threshold: int = 60
    ) -> List[Dict[str, Any]]:
        """Calculate fuzzy matches between source columns and target fields.
        
        This is a lightweight operation suitable for column-level matching.
        For account-level matching on large datasets, use the job queue.
        """
        mappings = []
        target_names = [f["name"] for f in target_fields]
        target_ids = [f["id"] for f in target_fields]
        
        for source_col in source_columns:
            # Try matching against field names
            name_match = process.extractOne(
                source_col,
                target_names,
                scorer=fuzz.WRatio,
                score_cutoff=threshold
            )
            
            # Try matching against field IDs
            id_match = process.extractOne(
                source_col.lower().replace(" ", "_"),
                target_ids,
                scorer=fuzz.WRatio,
                score_cutoff=threshold
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
            
            # Check for exact match
            source_normalized = source_col.lower().replace(" ", "_").replace("-", "_")
            for i, tid in enumerate(target_ids):
                if source_normalized == tid.lower() or source_col.lower() == target_names[i].lower():
                    best_match = tid
                    best_score = 100
                    match_type = "exact"
                    break
            
            if best_match:
                mappings.append({
                    "source_field": source_col,
                    "target_field": best_match,
                    "confidence": best_score,
                    "method": match_type
                })
            else:
                mappings.append({
                    "source_field": source_col,
                    "target_field": "",
                    "confidence": 0,
                    "method": "unmatched"
                })
        
        return mappings
    
    def find_best_target_name(
        self,
        source_name: str,
        target_names: List[str],
        threshold: int = 50
    ) -> Tuple[str, float]:
        """Find the best matching target name using fuzzy matching."""
        if not target_names or not source_name:
            return source_name, 0
        
        # Try exact match first
        source_lower = source_name.lower().strip()
        for tn in target_names:
            if tn.lower().strip() == source_lower:
                return tn, 100
        
        # Fuzzy match
        match = process.extractOne(
            source_name,
            target_names,
            scorer=fuzz.WRatio,
            score_cutoff=threshold
        )
        if match:
            return match[0], match[1]
        
        # Default to source name with low confidence
        return source_name, 0
    
    def create_hierarchical_mapping(
        self,
        source_data: List[Dict[str, Any]],
        target_data: Optional[List[Dict[str, Any]]],
        source_erp: str,
        target_erp: str
    ) -> Dict[str, Any]:
        """Create hierarchical mapping grouped by account type.
        
        This processes the data and creates grouped mappings.
        For very large datasets, this should be handled asynchronously.
        """
        # Get type mappings
        mapping_key = f"{source_erp}_to_{target_erp}"
        type_mappings = erp_service.ACCOUNT_TYPE_MAPPINGS.get(mapping_key, {})
        target_types = erp_service.get_account_types(target_erp)
        
        # Detect columns from source data
        type_col = None
        name_col = None
        number_col = None
        
        if source_data:
            for col in source_data[0].keys():
                col_lower = col.lower()
                if ('type' in col_lower and 'detail' not in col_lower) or col_lower == 'type':
                    type_col = col
                if 'name' in col_lower or 'title' in col_lower:
                    name_col = col
                if 'number' in col_lower or col_lower == 'number' or ('account' in col_lower and 'no' in col_lower):
                    number_col = col
        
        # Extract target account names
        target_names = []
        if target_data:
            target_name_col = None
            for col in target_data[0].keys():
                col_lower = col.lower()
                if 'name' in col_lower or 'title' in col_lower:
                    target_name_col = col
                    break
            
            if target_name_col:
                target_names = [
                    str(row.get(target_name_col, '')).strip()
                    for row in target_data
                    if row.get(target_name_col)
                ]
        
        # Group accounts by type
        grouped = {}
        for row in source_data:
            account_type = str(row.get(type_col, "Unknown")) if type_col else "Unknown"
            account_name = str(row.get(name_col, "")) if name_col else ""
            account_number = str(row.get(number_col, "")) if number_col else ""
            
            if account_type not in grouped:
                # Find best matching target type
                suggested_target = type_mappings.get(account_type, "")
                confidence = 100 if account_type in type_mappings else 0
                
                if not suggested_target and target_types:
                    match = process.extractOne(
                        account_type,
                        target_types,
                        scorer=fuzz.WRatio,
                        score_cutoff=50
                    )
                    if match:
                        suggested_target = match[0]
                        confidence = match[1]
                
                grouped[account_type] = {
                    "source_type": account_type,
                    "target_type": suggested_target,
                    "confidence": confidence,
                    "accounts": []
                }
            
            # Auto-populate target name
            best_target_name, name_confidence = self.find_best_target_name(
                account_name, target_names
            )
            
            grouped[account_type]["accounts"].append({
                "source_number": account_number,
                "source_name": account_name,
                "target_name": best_target_name,
                "name_confidence": name_confidence,
                "row_data": row
            })
        
        return {
            "type_column": type_col,
            "name_column": name_col,
            "number_column": number_col,
            "target_types": target_types,
            "grouped_mappings": list(grouped.values()),
            "total_accounts": sum(len(g["accounts"]) for g in grouped.values()),
            "total_types": len(grouped)
        }


# Singleton instance
matching_service = MatchingService()
