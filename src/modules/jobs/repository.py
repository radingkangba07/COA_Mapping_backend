from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from src.core.base_repository import BaseRepository
from src.modules.jobs.models import Job


class JobRepository(BaseRepository[Job]):
    model = Job

    async def create_job(
        self,
        project_id: UUID,
        job_type: str,
        input_data: dict | None = None,
        source_file_id: UUID | None = None,
        target_file_id: UUID | None = None,
        mapping_file_id: UUID | None = None,
        account_type_mapping_file_id: UUID | None = None,
        triggered_by: UUID | None = None,
    ) -> Job:
        job = Job(
            project_id=project_id,
            job_type=job_type,
            input_data=input_data,
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            mapping_file_id=mapping_file_id,
            account_type_mapping_file_id=account_type_mapping_file_id,
            triggered_by=triggered_by,
        )
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def update_status(self, job_id: UUID, status: str, **kwargs) -> Job | None:
        job = await self.get_by_id(job_id)
        if not job:
            return None
        job.status = status
        if status == "processing" and not job.started_at:
            job.started_at = datetime.now(UTC)
        if status in ("completed", "failed"):
            job.completed_at = datetime.now(UTC)
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        await self.session.flush()
        return job

    async def list_by_project(self, project_id: UUID, status: str | None = None, limit: int = 100) -> list[Job]:
        query = select(Job).where(Job.project_id == project_id)
        if status:
            query = query.where(Job.status == status)
        query = query.order_by(Job.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
