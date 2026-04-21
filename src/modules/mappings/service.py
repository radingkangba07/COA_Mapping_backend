import io
import logging
from collections import defaultdict
from uuid import UUID

import pandas as pd
from coa_db_models.mappings.models import CoaMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.mappings.repository import MappingRepository
from src.modules.mappings.schemas import MappingBulkSaveResponse, MappingStatsResponse, MappingUpdate, MappingUpsert
from src.modules.projects.dependencies import (
    authorize_for_resource,
    authorize_for_resources,
    ensure_project_access,
)
from src.modules.projects.repository import ProjectRepository

logger = logging.getLogger(__name__)


class MappingService:
    def __init__(
        self,
        mapping_repo: MappingRepository,
        project_repo: ProjectRepository,
        session: AsyncSession,
    ):
        self.mapping_repo = mapping_repo
        self.project_repo = project_repo
        self.session = session

    async def bulk_save(self, project_id: UUID, mappings: list[MappingUpsert]) -> MappingBulkSaveResponse:
        result = await self.mapping_repo.bulk_upsert(project_id, mappings)
        if result["missing_ids"]:
            raise NotFoundError(f"Mappings not found in project {project_id}: {result['missing_ids']}")
        # Auto-transition draft → in_progress
        project = await self.project_repo.get_by_id(project_id)
        if project and project.status == "draft":
            await self.project_repo.update_status(project_id, "in_progress")
        await self.session.commit()
        total = result["inserted"] + result["updated"]
        logger.info(
            "Upserted mappings for project %s (inserted=%d, updated=%d)",
            project_id,
            result["inserted"],
            result["updated"],
        )
        return MappingBulkSaveResponse(
            mapping_count=total,
            project_id=project_id,
            inserted=result["inserted"],
            updated=result["updated"],
        )

    async def list_mappings(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMapping]:
        return await self.mapping_repo.list_by_project(project_id, status, source_type, skip, limit)

    async def list_mappings_grouped(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        flat_mappings = await self.mapping_repo.list_by_project(project_id, status, source_type, skip, limit)

        groups: dict[tuple, list] = defaultdict(list)
        group_scores: dict[tuple, list[float]] = defaultdict(list)

        for m in flat_mappings:
            key = (m.source_account_type or "", m.target_account_type or "")
            score = m.confidence_score
            groups[key].append(
                {
                    "id": str(m.id),
                    "source_number": m.source_account_number or "",
                    "source_name": m.source_account_name,
                    "target_name": m.target_account_name or "",
                    "score": score,
                    "remark": m.mapping_source,
                    "mapping_source": m.mapping_source,
                    "status": m.mapping_status,
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

    async def update_mapping(self, mapping_id: UUID, data: MappingUpdate, user_id: UUID) -> CoaMapping:
        mapping = await self.mapping_repo.get_by_id(mapping_id)
        await authorize_for_resource(mapping, self.session, user_id, "editor", "Mapping not found")
        assert mapping is not None
        update_data = data.model_dump(exclude_unset=True)
        update_data["mapping_source"] = "user"
        mapping = await self.mapping_repo.update(mapping, update_data)
        await self.session.commit()
        return mapping

    async def bulk_update_status(self, mapping_ids: list[UUID], updates: MappingUpdate, user_id: UUID) -> int:
        update_data = updates.model_dump(exclude_unset=True)
        if "mapping_status" not in update_data:
            return 0
        rows = await self.mapping_repo.get_by_ids(mapping_ids)
        await authorize_for_resources(rows, self.session, user_id, "editor")
        count = await self.mapping_repo.bulk_update_status(mapping_ids, update_data["mapping_status"])
        await self.session.commit()
        return count

    async def delete_mapping(self, mapping_id: UUID, user_id: UUID) -> None:
        mapping = await self.mapping_repo.get_by_id(mapping_id)
        await authorize_for_resource(mapping, self.session, user_id, "editor", "Mapping not found")
        assert mapping is not None
        await self.mapping_repo.update(mapping, {"is_active": False})
        await self.session.commit()

    async def bulk_update_by_score(
        self, project_id: UUID, min_score: float, max_score: float, new_status: str, user_id: UUID
    ) -> dict:
        await ensure_project_access(self.session, user_id, project_id, "editor")
        result = await self.mapping_repo.update_by_score_range(project_id, min_score, max_score, new_status)
        await self.session.commit()
        return {"matched": result["matched"], "modified": result["modified"], "status": new_status}

    async def get_stats(self, project_id: UUID) -> MappingStatsResponse:
        stats = await self.mapping_repo.stats_by_status(project_id)
        return MappingStatsResponse(**stats)

    async def export_to_excel(self, project_id: UUID) -> bytes:
        mappings = await self.mapping_repo.list_by_project(project_id, limit=10000)
        data = []
        for m in mappings:
            data.append(
                {
                    "Source Account Number": m.source_account_number or "",
                    "Source Account Name": m.source_account_name,
                    "Source Account Type": m.source_account_type or "",
                    "Target Account Number": m.target_account_number or "",
                    "Target Account Name": m.target_account_name or "",
                    "Target Account Type": m.target_account_type or "",
                    "Confidence Score": m.confidence_score,
                    "Status": m.mapping_status,
                    "Source": m.mapping_source,
                    "Notes": m.notes or "",
                    "approval_scope": "",
                    "project_id": str(m.project_id),
                }
            )
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        return buffer.getvalue()
