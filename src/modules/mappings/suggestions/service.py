import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.mappings.suggestions.repository import SuggestionRepository

logger = logging.getLogger(__name__)


class SuggestionService:
    def __init__(self, repo: SuggestionRepository, session: AsyncSession):
        self.repo = repo
        self.session = session

    async def list_suggestions_grouped(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        suggestions = await self.repo.list_by_project(project_id, status, source_type, skip, limit)

        groups: dict[tuple, list] = defaultdict(list)
        group_scores: dict[tuple, list[float]] = defaultdict(list)

        for s in suggestions:
            key = (s.source_account_type or "", s.target_account_type or "")
            score = float(s.confidence_score)
            groups[key].append(
                {
                    "id": str(s.id),
                    "source_name": s.source_account_name or "",
                    "target_name": s.target_account_name or "",
                    "score": score,
                    "status": s.mapping_status,
                    "mapping_source": s.mapping_source,
                }
            )
            group_scores[key].append(score)

        return [
            {
                "source_type": source_type_val,
                "target_type": target_type_val,
                "confidence": round(sum(scores) / len(scores), 1) if scores else 0,
                "accounts": groups[(source_type_val, target_type_val)],
            }
            for (source_type_val, target_type_val), scores in group_scores.items()
        ]
