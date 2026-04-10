import json
import logging

from nats.js import JetStreamContext

from src.modules.jobs.models import Job

logger = logging.getLogger(__name__)


class NATSPublisher:
    def __init__(self, jetstream: JetStreamContext):
        self.js = jetstream

    async def publish_job(self, job: Job) -> None:
        subject = "jobs.mapping.run"
        payload = json.dumps(
            {
                "job_id": str(job.id),
                "project_id": str(job.project_id),
                "company_id": str(job.input_data.get("company_id", "")) if job.input_data else "",
                "source_file_id": str(job.source_file_id) if job.source_file_id else None,
                "target_file_id": str(job.target_file_id) if job.target_file_id else None,
                "mapping_file_id": str(job.mapping_file_id) if job.mapping_file_id else None,
            }
        ).encode()
        await self.js.publish(subject, payload)
        logger.info("Published job %s to %s (project=%s)", job.id, subject, job.project_id)
