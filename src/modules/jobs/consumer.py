import asyncio
import json
import logging
from datetime import datetime
from uuid import UUID

from nats.js import JetStreamContext

from src.core.config import get_settings
from src.modules.jobs.protocols import JobRepositoryProtocol

logger = logging.getLogger(__name__)


class NATSConsumer:
    def __init__(self, jetstream: JetStreamContext, job_repo: JobRepositoryProtocol, session=None):
        self.js = jetstream
        self.job_repo = job_repo
        self.session = session

    async def start(self) -> None:
        subject = get_settings().nats_subject_results
        self.sub = await self.js.subscribe(subject, durable="api-result-consumer", manual_ack=True)
        asyncio.create_task(self._consume())
        logger.info("NATS result consumer started, listening on %s", subject)

    async def _consume(self) -> None:
        async for msg in self.sub.messages:
            try:
                data = json.loads(msg.data.decode())
                logger.info("Received result for job %s (status=%s)", data.get("job_id"), data.get("status"))
                await self._handle_result(data)
                if self.session:
                    await self.session.commit()
                await msg.ack()
            except Exception:
                logger.exception("Failed to process result message")
                await msg.nak(delay=5)

    async def _handle_result(self, data: dict) -> None:
        job_id = UUID(data["job_id"])
        status = data["status"]

        if status in ("completed", "failed"):
            await self.job_repo.update_status(
                job_id=job_id,
                status=status,
                progress=100.0 if status == "completed" else 0.0,
                result_data=data.get("result_data"),
                error_message=data.get("error_message"),
            )
            logger.info("Job %s %s", job_id, status)
        elif status == "running":
            await self.job_repo.update_status(
                job_id=job_id,
                status="processing",
                progress=data.get("progress", 0.0),
                message=data.get("message"),
            )
            logger.info("Job %s processing", job_id)
        else:
            await self.job_repo.update_status(
                job_id=job_id,
                status=status,
                progress=data.get("progress", 0.0),
            )
            logger.info("Job %s status=%s", job_id, status)
