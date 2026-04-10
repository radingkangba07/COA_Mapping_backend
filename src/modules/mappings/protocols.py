from typing import Protocol
from uuid import UUID

from src.modules.mappings.models import Mapping
from src.modules.mappings.schemas import MappingCreate, MappingUpdate


class MappingRepositoryProtocol(Protocol):
    async def bulk_replace(self, project_id: UUID, mappings: list[MappingCreate]) -> int: ...
    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Mapping]: ...
    async def get_by_id(self, mapping_id: UUID) -> Mapping | None: ...
    async def update(self, mapping_id: UUID, data: MappingUpdate) -> Mapping: ...
    async def bulk_update_status(self, mapping_ids: list[UUID], status: str) -> int: ...
    async def delete(self, mapping_id: UUID) -> None: ...
    async def count_by_project(self, project_id: UUID) -> int: ...
    async def stats_by_status(self, project_id: UUID) -> dict[str, int]: ...


class MatchingEngineProtocol(Protocol):
    def fuzzy_match_columns(
        self,
        source_columns: list[str],
        target_fields: list[dict],
        threshold: int = 60,
    ) -> list[dict]: ...
    def find_best_target_name(
        self,
        source_name: str,
        target_names: list[str],
        threshold: int = 60,
    ) -> tuple[str, float]: ...
