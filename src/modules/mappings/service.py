import io
import logging
from uuid import UUID

import pandas as pd
from coa_db_models.mappings.models import CoaMapping
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.modules.mappings.repository import MappingRepository
from src.modules.mappings.schemas import MappingBulkSaveResponse, MappingCreate, MappingStatsResponse, MappingUpdate
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

    async def bulk_save(self, project_id: UUID, mappings: list[MappingCreate]) -> MappingBulkSaveResponse:
        count = await self.mapping_repo.bulk_replace(project_id, mappings)
        # Auto-transition draft → in_progress
        project = await self.project_repo.get_by_id(project_id)
        if project and project.status == "draft":
            await self.project_repo.update_status(project_id, "in_progress")
        await self.session.commit()
        logger.info("Bulk saved %d mappings for project %s", count, project_id)
        return MappingBulkSaveResponse(mapping_count=count, project_id=project_id)

    async def list_mappings(
        self,
        project_id: UUID,
        status: str | None = None,
        source_type: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CoaMapping]:
        return await self.mapping_repo.list_by_project(project_id, status, source_type, skip, limit)

    async def update_mapping(self, mapping_id: UUID, data: MappingUpdate) -> CoaMapping:
        mapping = await self.mapping_repo.get_by_id(mapping_id)
        if not mapping:
            raise NotFoundError("Mapping not found")
        update_data = data.model_dump(exclude_unset=True)
        update_data["mapping_source"] = "user"
        mapping = await self.mapping_repo.update(mapping, update_data)
        await self.session.commit()
        return mapping

    async def bulk_update_status(self, mapping_ids: list[UUID], updates: MappingUpdate) -> int:
        update_data = updates.model_dump(exclude_unset=True)
        if "mapping_status" not in update_data:
            return 0
        count = await self.mapping_repo.bulk_update_status(mapping_ids, update_data["mapping_status"])
        await self.session.commit()
        return count

    async def delete_mapping(self, mapping_id: UUID) -> None:
        await self.mapping_repo.delete(mapping_id)
        await self.session.commit()

    async def bulk_update_by_score(self, project_id: UUID, min_score: float, max_score: float, new_status: str) -> dict:
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
