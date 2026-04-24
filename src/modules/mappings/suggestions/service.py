import logging
from collections import defaultdict
from uuid import UUID

from coa_db_models.mappings.models import CoaMapping, CoaMappingSuggestion
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.mappings.suggestions.repository import SuggestionRepository

logger = logging.getLogger(__name__)


def _merge(suggestion: CoaMappingSuggestion, mapping: CoaMapping | None) -> dict:
    """Mapping wins; suggestion fills any fields the mapping doesn't have."""
    if mapping is None:
        return {
            "id": None,  # no mapping yet — FE must send suggestion_id on save to create + link
            "suggestion_id": str(suggestion.id),
            "source_name": suggestion.source_account_name or "",
            "source_type": suggestion.source_account_type or "",
            "target_name": suggestion.target_account_name or "",
            "target_type": suggestion.target_account_type or "",
            "status": suggestion.mapping_status,
            "mapping_source": suggestion.mapping_source,
            "score": float(suggestion.confidence_score),
        }
    return {
        "id": str(mapping.id),
        "suggestion_id": str(suggestion.id),
        "source_name": mapping.source_account_name or suggestion.source_account_name or "",
        "source_type": mapping.source_account_type or suggestion.source_account_type or "",
        "target_name": mapping.target_account_name or suggestion.target_account_name or "",
        "target_type": mapping.target_account_type or suggestion.target_account_type or "",
        "status": mapping.mapping_status or suggestion.mapping_status,
        "mapping_source": mapping.mapping_source or suggestion.mapping_source,
        "score": float(
            mapping.confidence_score if mapping.confidence_score is not None else suggestion.confidence_score
        ),
    }


class SuggestionService:
    def __init__(self, repo: SuggestionRepository, session: AsyncSession):
        self.repo = repo
        self.session = session

    async def list_suggestions_grouped(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
    ) -> dict:
        rows = await self.repo.list_by_project_with_mappings(project_id, status, source_type)

        groups: dict[tuple, list] = defaultdict(list)
        group_scores: dict[tuple, list[float]] = defaultdict(list)

        for suggestion, mapping in rows:
            merged = _merge(suggestion, mapping)
            key = (merged["source_type"], merged["target_type"])
            groups[key].append(
                {
                    "id": merged["id"],
                    "suggestion_id": merged["suggestion_id"],
                    "source_name": merged["source_name"],
                    "target_name": merged["target_name"],
                    "score": merged["score"],
                    "status": merged["status"],
                    "mapping_source": merged["mapping_source"],
                }
            )
            group_scores[key].append(merged["score"])

        grouped = [
            {
                "source_type": source_type_val,
                "target_type": target_type_val,
                "confidence": round(sum(scores) / len(scores), 1) if scores else 0,
                "accounts": groups[(source_type_val, target_type_val)],
            }
            for (source_type_val, target_type_val), scores in group_scores.items()
        ]

        return {"total": len(rows), "groups": grouped}
