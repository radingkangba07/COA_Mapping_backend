import asyncio
import json
import logging
from uuid import UUID

from nats.js import JetStreamContext

from src.modules.jobs.protocols import JobRepositoryProtocol

logger = logging.getLogger(__name__)


class NATSConsumer:
    def __init__(self, jetstream: JetStreamContext, job_repo: JobRepositoryProtocol):
        self.js = jetstream
        self.job_repo = job_repo

    async def start(self) -> None:
        self.sub = await self.js.subscribe("coa.results.*", durable="api-result-consumer", manual_ack=True)
        asyncio.create_task(self._consume())

    async def _consume(self) -> None:
        async for msg in self.sub.messages:
            try:
                data = json.loads(msg.data.decode())
                await self._handle_result(data)
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
                progress=data.get("progress", 100.0),
                result_data=data.get("result_data"),
                error_message=data.get("error_message"),
            )
        else:
            await self.job_repo.update_status(
                job_id=job_id,
                status="processing",
                progress=data.get("progress", 0.0),
                message=data.get("message"),
            )
