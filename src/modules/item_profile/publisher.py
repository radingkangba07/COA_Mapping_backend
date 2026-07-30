import json
import logging
from uuid import UUID

from nats.js import JetStreamContext

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class ItemProfilePublisher:
    def __init__(self, jetstream: JetStreamContext):
        self.js = jetstream

    async def publish_run_created(self, run_id: UUID, project_id: UUID) -> None:
        subject = get_settings().nats_job_item_profile_run
        payload = json.dumps({"run_id": str(run_id), "project_id": str(project_id)}).encode()
        await self.js.publish(subject, payload)
        logger.info("Published %s for run %s (project=%s)", subject, run_id, project_id)
