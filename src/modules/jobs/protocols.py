from typing import Protocol
from uuid import UUID

from src.modules.jobs.models import Job


class QueueProtocol(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None: ...


class JobRepositoryProtocol(Protocol):
    async def create(self, project_id: UUID, job_type: str, input_data: dict | None = None) -> Job: ...
    async def get_by_id(self, job_id: UUID) -> Job | None: ...
    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Job]: ...
    async def update_status(self, job_id: UUID, status: str, **kwargs) -> Job | None: ...
    async def delete(self, job_id: UUID) -> None: ...
