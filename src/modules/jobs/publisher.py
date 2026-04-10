import json
import logging
from datetime import UTC, datetime

from nats.js import JetStreamContext

from src.core.config import get_settings
from src.modules.jobs.models import Job

logger = logging.getLogger(__name__)


class NATSPublisher:
    def __init__(self, jetstream: JetStreamContext):
        self.js = jetstream

    async def publish_job(self, job: Job) -> None:
        subject = get_settings().nats_subject_job_run
        metadata = job.input_data or {}
        payload = json.dumps(
            {
                "job_id": str(job.id),
                "project_id": str(job.project_id),
                "company_id": metadata.get("company_id", ""),
                "job_type": job.job_type,
                "source_file_id": str(job.source_file_id) if job.source_file_id else None,
                "target_file_id": str(job.target_file_id) if job.target_file_id else None,
                "mapping_file_id": str(job.mapping_file_id) if job.mapping_file_id else None,
                "account_type_mapping_file_id": str(job.account_type_mapping_file_id) if job.account_type_mapping_file_id else None,
                "triggered_by": str(job.triggered_by) if job.triggered_by else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "event_at": datetime.now(UTC).isoformat(),
                "metadata": {
                    "source_system": metadata.get("source_system"),
                    "target_system": metadata.get("target_system"),
                },
            }
        ).encode()
        await self.js.publish(subject, payload)
        logger.info("Published job %s to %s (project=%s)", job.id, subject, job.project_id)
