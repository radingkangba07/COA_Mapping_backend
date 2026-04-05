"""Job service for managing async jobs."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus, JobType
from app.services.queue_service import queue_service


class JobService:
    """Service for managing processing jobs."""
    
    async def create_job(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        job_type: str,
        input_data: Optional[Dict[str, Any]] = None
    ) -> Job:
        """Create a new job and optionally queue it."""
        job = Job(
            project_id=project_id,
            job_type=job_type,
            status=JobStatus.PENDING.value,
            input_data=input_data
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        
        # Queue the job for processing
        if job_type == JobType.ACCOUNT_MATCHING.value:
            queued = await self._queue_matching_job(job)
            if queued:
                job.status = JobStatus.QUEUED.value
                await db.commit()
        
        return job
    
    async def get_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID
    ) -> Optional[Job]:
        """Get a job by ID."""
        result = await db.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()
    
    async def get_project_jobs(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        limit: int = 100
    ) -> List[Job]:
        """Get jobs for a project."""
        result = await db.execute(
            select(Job)
            .where(Job.project_id == project_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_job_status(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        status: str,
        progress: float = None,
        message: str = None,
        result_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> Optional[Job]:
        """Update job status."""
        job = await self.get_job(db, job_id)
        if not job:
            return None
        
        job.status = status
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if result_data is not None:
            job.result_data = result_data
        if error_message is not None:
            job.error_message = error_message
        
        # Set timestamps
        if status == JobStatus.PROCESSING.value and not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        if status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value]:
            job.completed_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(job)
        return job
    
    async def _queue_matching_job(self, job: Job) -> bool:
        """Queue a matching job to RabbitMQ.
        
        Returns True if successfully queued, False otherwise.
        """
        message = {
            "job_id": str(job.id),
            "project_id": str(job.project_id),
            "job_type": job.job_type,
            "input_data": job.input_data,
            "created_at": job.created_at.isoformat()
        }
        
        return await queue_service.publish_job(message)
    
    def get_job_status_response(self, job: Job) -> Dict[str, Any]:
        """Format job for status polling response."""
        return {
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "is_complete": job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value],
            "has_error": job.status == JobStatus.FAILED.value,
            "result_available": job.result_data is not None
        }
