from typing import Protocol
from uuid import UUID

from src.modules.jobs.models import Job


class QueueProtocol(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None: ...


class JobRepositoryProtocol(Protocol):
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
    ) -> Job: ...
    async def get_by_id(self, id: UUID) -> Job | None: ...
    async def list_by_project(
        self,
        project_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Job]: ...
    async def update_status(self, job_id: UUID, status: str, **kwargs) -> Job | None: ...
    async def delete(self, id: UUID) -> None: ...
