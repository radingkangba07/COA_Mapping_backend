"""Unit tests for NATS result consumer message handling."""

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from src.modules.jobs.consumer import NATSConsumer


def _mock_msg(data: dict) -> AsyncMock:
    msg = AsyncMock()
    msg.data = json.dumps(data).encode()
    return msg


@pytest.mark.asyncio
async def test_handle_completed_result():
    """Consumer updates job to completed with result_data."""
    mock_js = AsyncMock()
    mock_repo = AsyncMock()
    consumer = NATSConsumer(mock_js, mock_repo)

    job_id = str(uuid.uuid4())
    await consumer._handle_result(
        {
            "job_id": job_id,
            "status": "completed",
            "progress": 100.0,
            "result_data": {"mapping_count": 42},
        }
    )

    mock_repo.update_status.assert_called_once_with(
        job_id=uuid.UUID(job_id),
        status="completed",
        progress=100.0,
        result_data={"mapping_count": 42},
        error_message=None,
    )


@pytest.mark.asyncio
async def test_handle_failed_result():
    """Consumer updates job to failed with error_message."""
    mock_js = AsyncMock()
    mock_repo = AsyncMock()
    consumer = NATSConsumer(mock_js, mock_repo)

    job_id = str(uuid.uuid4())
    await consumer._handle_result(
        {
            "job_id": job_id,
            "status": "failed",
            "error_message": "File not found in R2",
        }
    )

    mock_repo.update_status.assert_called_once_with(
        job_id=uuid.UUID(job_id),
        status="failed",
        progress=0.0,
        result_data=None,
        error_message="File not found in R2",
    )


@pytest.mark.asyncio
async def test_handle_running_result():
    """Consumer maps 'running' status to 'processing'."""
    mock_js = AsyncMock()
    mock_repo = AsyncMock()
    consumer = NATSConsumer(mock_js, mock_repo)

    job_id = str(uuid.uuid4())
    await consumer._handle_result(
        {
            "job_id": job_id,
            "status": "running",
            "progress": 45.0,
            "message": "Matching accounts...",
        }
    )

    mock_repo.update_status.assert_called_once_with(
        job_id=uuid.UUID(job_id),
        status="processing",
        progress=45.0,
        message="Matching accounts...",
    )


@pytest.mark.asyncio
async def test_handle_result_defaults():
    """Missing progress/result_data use defaults."""
    mock_js = AsyncMock()
    mock_repo = AsyncMock()
    consumer = NATSConsumer(mock_js, mock_repo)

    job_id = str(uuid.uuid4())
    await consumer._handle_result(
        {
            "job_id": job_id,
            "status": "completed",
        }
    )

    mock_repo.update_status.assert_called_once_with(
        job_id=uuid.UUID(job_id),
        status="completed",
        progress=100.0,
        result_data=None,
        error_message=None,
    )
