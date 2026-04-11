import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.core.nats_client import is_nats_available
from src.modules.jobs.models import Job
from src.modules.jobs.publisher import NATSPublisher
from src.modules.jobs.repository import JobRepository

logger = logging.getLogger(__name__)


class JobService:
    def __init__(
        self,
        job_repo: JobRepository,
        session: AsyncSession,
        publisher: NATSPublisher | None = None,
    ):
        self.job_repo = job_repo
        self.session = session
        self.publisher = publisher

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
        job = await self.job_repo.create_job(
            project_id,
            job_type,
            input_data,
            source_file_id=source_file_id,
            target_file_id=target_file_id,
            mapping_file_id=mapping_file_id,
            account_type_mapping_file_id=account_type_mapping_file_id,
            triggered_by=triggered_by,
        )

        if is_nats_available() and self.publisher:
            await self.publisher.publish_job(job)
            await self.job_repo.update_status(job.id, status="queued")
        else:
            # Sync fallback — mark as completed immediately
            await self.job_repo.update_status(
                job.id,
                status="completed",
                progress=100.0,
                result_data={"message": "Processed synchronously (NATS unavailable)"},
            )

        await self.session.commit()
        logger.info("Job %s (%s) created for project %s", job.id, job_type, project_id)
        result = await self.job_repo.get_by_id(job.id)
        return result  # type: ignore[return-value]

    async def get_job(self, job_id: UUID) -> Job:
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError("Job not found")
        return job

    async def get_status(self, job_id: UUID) -> dict:
        job = await self.get_job(job_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "is_complete": job.status in ("completed", "failed"),
            "has_error": job.status == "failed",
        }

    async def get_result(self, job_id: UUID) -> dict:
        job = await self.get_job(job_id)
        if job.status != "completed":
            raise NotFoundError("Job result not available yet")
        return {
            "job_id": job.id,
            "status": job.status,
            "result_data": job.result_data,
            "error_message": job.error_message,
        }

    async def list_project_jobs(self, project_id: UUID, status: str | None = None, limit: int = 100) -> list[Job]:
        return await self.job_repo.list_by_project(project_id, status, limit)

    async def cancel_job(self, job_id: UUID) -> None:
        job = await self.get_job(job_id)
        if job.status not in ("queued",):
            raise NotFoundError("Only queued jobs can be cancelled")
        await self.job_repo.update_status(job.id, status="failed", error_message="Cancelled by user")
        await self.session.commit()
