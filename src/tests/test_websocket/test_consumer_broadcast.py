"""Unit tests: NATSConsumer reads DB and broadcasts authoritative job state.

The ML worker writes the terminal status to the jobs table, then publishes
{job_id} on NATS. The consumer fetches the job and broadcasts to WS clients.
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
async def test_broadcasts_completed_payload():
    project_id = uuid.uuid4()
    job = _make_job(project_id, "completed")

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = job
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(job.id)})

    target_project, payload = mock_manager.broadcast.call_args.args
    assert target_project == project_id
    assert payload == {"job_id": str(job.id), "status": "completed"}


@pytest.mark.asyncio
async def test_broadcasts_failed_payload_with_error_from_db():
    project_id = uuid.uuid4()
    job = _make_job(project_id, "failed", error_message="ML worker crashed")

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = job
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(job.id)})

    _, payload = mock_manager.broadcast.call_args.args
    assert payload["status"] == "failed"
    assert payload["error_message"] == "ML worker crashed"


@pytest.mark.asyncio
async def test_no_broadcast_when_manager_is_none():
    job = _make_job(uuid.uuid4(), "completed")

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = job

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=None)

    # Should not raise
    await consumer._handle_result({"job_id": str(job.id)})


@pytest.mark.asyncio
async def test_no_broadcast_when_job_not_found():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    mock_manager = AsyncMock()

    consumer = NATSConsumer(jetstream=AsyncMock(), job_repo=mock_repo, connection_manager=mock_manager)

    await consumer._handle_result({"job_id": str(uuid.uuid4())})

    mock_manager.broadcast.assert_not_awaited()
