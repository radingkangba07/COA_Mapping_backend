from typing import cast
from uuid import UUID

from coa_db_models.mappings.models import CoaMapping, CoaMappingSuggestion
from sqlalchemy import CursorResult, func, select, update

from src.core.base_repository import BaseRepository
from src.modules.mappings.schemas import MappingUpsert

_SUGGESTION_COPY_FIELDS = (
    "source_account_name",
    "source_account_type",
    "target_account_name",
    "target_account_type",
    "confidence_score",
    "mapping_status",
    "mapping_source",
    "source_to_map",
    "source_row_id",
    "target_row_id",
    "unique_identifier",
    "notes",
)


class MappingRepository(BaseRepository[CoaMapping]):
    model = CoaMapping

    @staticmethod
    def _merge_from_suggestion(data: dict, suggestion: CoaMappingSuggestion | None) -> dict:
        """FE-provided fields win; missing fields copied from the suggestion row."""
        if suggestion is None:
            return data
        merged = dict(data)
        for field in _SUGGESTION_COPY_FIELDS:
            if field not in merged:
                value = getattr(suggestion, field, None)
                if value is not None:
                    merged[field] = value
        return merged

    async def bulk_upsert(self, project_id: UUID, mappings: list[MappingUpsert]) -> dict:
        """Upsert mappings with suggestion-aware resolution (all scoped to project_id).

        Resolution per row:
          1. `suggestion_id` given → look up suggestion.coa_mapping_id.
             - If set → UPDATE that mapping (idempotent; FE can resend suggestion_id safely).
             - If null → INSERT new mapping + set suggestion.coa_mapping_id.
          2. Else `id` given → UPDATE that mapping directly.
          3. Else → INSERT a manual mapping (no suggestion link).

        Returns {"inserted": int, "updated": int, "missing_ids": list[UUID]}.
        Caller raises NotFoundError if missing_ids is non-empty.
        """
        inserted = 0
        updated = 0
        missing_ids: list[UUID] = []
        pending_links: list[tuple[CoaMapping, UUID]] = []  # (new_mapping, suggestion_id)

        for m in mappings:
            data = m.model_dump(exclude_unset=True, exclude={"id", "suggestion_id"})
            # If FE didn't specify is_active, default to active (a plain save means "confirm").
            # Delete flows send is_active=False explicitly.
            if "is_active" not in data:
                data["is_active"] = True

            if m.suggestion_id is not None:
                suggestion = await self.session.scalar(
                    select(CoaMappingSuggestion).where(
                        CoaMappingSuggestion.id == m.suggestion_id,
                        CoaMappingSuggestion.project_id == project_id,
                    )
                )
                existing_mapping_id = suggestion.coa_mapping_id if suggestion else None
                if existing_mapping_id is not None:
                    result = await self.session.execute(
                        update(CoaMapping)
                        .where(CoaMapping.id == existing_mapping_id, CoaMapping.project_id == project_id)
                        .values(**data)
                    )
                    if cast(CursorResult, result).rowcount == 0:
                        missing_ids.append(existing_mapping_id)
                    else:
                        updated += 1
                else:
                    # Insert new mapping — fill missing fields from the suggestion row.
                    insert_data = self._merge_from_suggestion(data, suggestion)
                    new_mapping = CoaMapping(project_id=project_id, **insert_data)
                    self.session.add(new_mapping)
                    pending_links.append((new_mapping, m.suggestion_id))
                    inserted += 1
            elif m.id is not None:
                result = await self.session.execute(
                    update(CoaMapping).where(CoaMapping.id == m.id, CoaMapping.project_id == project_id).values(**data)
                )
                if cast(CursorResult, result).rowcount == 0:
                    missing_ids.append(m.id)
                else:
                    updated += 1
            else:
                self.session.add(CoaMapping(project_id=project_id, **data))
                inserted += 1

        await self.session.flush()  # assigns PKs so we can link suggestions

        for mapping, suggestion_id in pending_links:
            await self.session.execute(
                update(CoaMappingSuggestion)
                .where(
                    CoaMappingSuggestion.id == suggestion_id,
                    CoaMappingSuggestion.project_id == project_id,
                )
                .values(coa_mapping_id=mapping.id)
            )

        await self.session.flush()
        return {"inserted": inserted, "updated": updated, "missing_ids": missing_ids}

    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMapping]:
        query = select(CoaMapping).where(
            CoaMapping.project_id == project_id,
            CoaMapping.is_active.is_(True),
        )
        if status:
            query = query.where(CoaMapping.mapping_status == status)
        if source_type:
            query = query.where(CoaMapping.source_account_type == source_type)
        query = query.offset(skip).limit(limit).order_by(CoaMapping.created_at)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_ids(self, mapping_ids: list[UUID]) -> list[CoaMapping]:
        if not mapping_ids:
            return []
        result = await self.session.execute(select(CoaMapping).where(CoaMapping.id.in_(mapping_ids)))
        return list(result.scalars().all())

    async def bulk_update_status(self, mapping_ids: list[UUID], status: str) -> int:
        if not mapping_ids:
            return 0
        result = await self.session.execute(
            update(CoaMapping).where(CoaMapping.id.in_(mapping_ids)).values(mapping_status=status)
        )
        await self.session.flush()
        rowcount: int = cast(CursorResult, result).rowcount
        return rowcount

    async def update_by_score_range(
        self, project_id: UUID, min_score: float, max_score: float, new_status: str
    ) -> dict:
        stmt = (
            update(CoaMapping)
            .where(
                CoaMapping.project_id == project_id,
                CoaMapping.confidence_score >= min_score,
                CoaMapping.confidence_score <= max_score,
            )
            .values(mapping_status=new_status)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        rowcount = cast(CursorResult, result).rowcount
        return {"matched": rowcount, "modified": rowcount}

    async def count_by_project(self, project_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(CoaMapping.id)).where(CoaMapping.project_id == project_id)
        )
        return result.scalar_one()

    async def stats_by_status(self, project_id: UUID) -> dict[str, int]:
        result = await self.session.execute(
            select(CoaMapping.mapping_status, func.count(CoaMapping.id))
            .where(CoaMapping.project_id == project_id)
            .group_by(CoaMapping.mapping_status)
        )
        stats = {"total": 0, "suggested": 0, "approved": 0, "rejected": 0, "modified": 0}
        for status, count in result.all():
            stats[status] = count
            stats["total"] += count
        return stats
