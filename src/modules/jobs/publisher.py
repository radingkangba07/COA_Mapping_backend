import json

from nats.js import JetStreamContext

from src.modules.jobs.models import Job


class NATSPublisher:
    def __init__(self, jetstream: JetStreamContext):
        self.js = jetstream

    async def publish_job(self, job: Job) -> None:
        subject = f"coa.jobs.{job.job_type}"
        payload = json.dumps(
            {
                "job_id": str(job.id),
                "project_id": str(job.project_id),
                "job_type": job.job_type,
                "input_data": job.input_data,
                "created_at": job.created_at.isoformat(),
            }
        ).encode()
        await self.js.publish(subject, payload)
