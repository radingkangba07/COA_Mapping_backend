"""Unit tests for NATS result consumer message handling.

Contract: ML worker writes final status (completed/failed) to the jobs table,
then publishes {job_id} on NATS. The consumer reads the DB and broadcasts.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.jobs.consumer import NATSConsumer


def _make_job(project_id: uuid.UUID, status: str, error_message: str | None = None) -> MagicMock:
    job = MagicMock()
    job.id = uuid.uuid4()
    job.project_id = project_id
    job.status = status
    job.error_message = error_message
    return job


@pytest.mark.asyncio
async def test_handle_completed_broadcasts_job_id_and_status():
    project_id = uuid.uuid4()
    job = _make_job(project_id, "completed")

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = job
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(job.id)})

    mock_repo.get_by_id.assert_awaited_once_with(job.id)
    mock_manager.broadcast.assert_awaited_once_with(project_id, {"job_id": str(job.id), "status": "completed"})


@pytest.mark.asyncio
async def test_handle_failed_broadcasts_error_message_from_db():
    project_id = uuid.uuid4()
    job = _make_job(project_id, "failed", error_message="File not found in R2")

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = job
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(job.id)})

    mock_manager.broadcast.assert_awaited_once_with(
        project_id,
        {"job_id": str(job.id), "status": "failed", "error_message": "File not found in R2"},
    )


@pytest.mark.asyncio
async def test_handle_unknown_job_skips_broadcast():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(uuid.uuid4())})

    mock_manager.broadcast.assert_not_awaited()
