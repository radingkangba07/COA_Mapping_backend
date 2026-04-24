from typing import Protocol
from uuid import UUID

from coa_db_models.mappings.models import CoaMappingSuggestion


class SuggestionRepositoryProtocol(Protocol):
    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMappingSuggestion]: ...
