import asyncio
import json
import logging

from nats.js import JetStreamContext

from src.core.config import get_settings
from src.modules.jobs.protocols import JobRepositoryProtocol
from src.modules.jobs.schemas import JobStatusNotification
from src.modules.websocket.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class NATSConsumer:
    def __init__(
        self,
        jetstream: JetStreamContext,
        job_repo: JobRepositoryProtocol,
        session=None,
        connection_manager: ConnectionManager | None = None,
    ):
        self.js = jetstream
        self.job_repo = job_repo
        self.session = session
        self.connection_manager = connection_manager
        self._consume_task: asyncio.Task | None = None

    async def start(self) -> None:
        settings = get_settings()
        subject = settings.nats_subject_results
        durable = settings.nats_durable_consumer
        try:
            self.sub = await self.js.subscribe(subject, durable=durable, manual_ack=True)
        except Exception:
            logger.warning("Durable consumer %s already bound, deleting stale subscription", durable)
            await self.js.delete_consumer(settings.nats_stream_name, durable)
            self.sub = await self.js.subscribe(subject, durable=durable, manual_ack=True)
        self._consume_task = asyncio.create_task(self._consume())
        logger.info("NATS result consumer started, listening on %s", subject)

    async def stop(self) -> None:
        logger.info("Stopping NATS result consumer")
        if self._consume_task is not None:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("NATS consumer task raised during shutdown")
            self._consume_task = None
        sub = getattr(self, "sub", None)
        if sub is not None:
            try:
                await sub.unsubscribe()
            except Exception:
                logger.exception("Failed to unsubscribe NATS consumer")
        if self.session is not None:
            try:
                await self.session.close()
            except Exception:
                logger.exception("Failed to close consumer DB session")
        logger.info("NATS result consumer stopped")

    async def _consume(self) -> None:
        async for msg in self.sub.messages:
            try:
                data = json.loads(msg.data.decode())
                logger.info("Received status notification for job %s", data.get("job_id"))
                await self._handle_result(data)
                await msg.ack()
            except Exception:
                logger.exception("Failed to process result message")
                await msg.nak(delay=5)

    async def _handle_result(self, data: dict) -> None:
        """ML worker writes terminal status to DB then publishes {job_id}.
        We read the DB and broadcast the authoritative state to WS clients.
        """
        notification = JobStatusNotification.model_validate(data)
        job = await self.job_repo.get_by_id(notification.job_id)
        if job is None:
            logger.warning("Status notification for unknown job %s", notification.job_id)
            return

        logger.info("Job %s status=%s", job.id, job.status)

        if self.connection_manager is None:
            return

        payload: dict = {"job_id": str(job.id), "status": job.status}
        if job.status == "failed":
            payload["error_message"] = job.error_message
        await self.connection_manager.broadcast(job.project_id, payload)
