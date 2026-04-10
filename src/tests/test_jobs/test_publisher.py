"""Unit tests for NATS job publisher payload structure."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.modules.jobs.publisher import NATSPublisher


def _make_job(**overrides) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "job_type": "account_matching",
        "status": "queued",
        "progress": 0.0,
        "input_data": {"company_id": str(uuid.uuid4())},
        "source_file_id": uuid.uuid4(),
        "target_file_id": uuid.uuid4(),
        "mapping_file_id": uuid.uuid4(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_publish_job_subject_and_payload():
    """Publisher sends to jobs.mapping.run with the correct payload shape."""
    mock_js = AsyncMock()
    publisher = NATSPublisher(mock_js)

    job = _make_job()
    await publisher.publish_job(job)

    mock_js.publish.assert_called_once()
    subject, payload = mock_js.publish.call_args.args
    assert subject == "jobs.mapping.run"

    data = json.loads(payload.decode())
    assert data["job_id"] == str(job.id)
    assert data["project_id"] == str(job.project_id)
    assert data["company_id"] == job.input_data["company_id"]
    assert data["source_file_id"] == str(job.source_file_id)
    assert data["target_file_id"] == str(job.target_file_id)
    assert data["mapping_file_id"] == str(job.mapping_file_id)


@pytest.mark.asyncio
async def test_publish_job_no_file_ids():
    """File IDs are None when not set on the job."""
    mock_js = AsyncMock()
    publisher = NATSPublisher(mock_js)

    job = _make_job(
        source_file_id=None,
        target_file_id=None,
        mapping_file_id=None,
        input_data=None,
    )
    await publisher.publish_job(job)

    data = json.loads(mock_js.publish.call_args.args[1].decode())
    assert data["source_file_id"] is None
    assert data["target_file_id"] is None
    assert data["mapping_file_id"] is None
    assert data["company_id"] == ""


@pytest.mark.asyncio
async def test_publish_job_payload_keys():
    """Payload contains exactly the keys Bhavna's ML service expects."""
    mock_js = AsyncMock()
    publisher = NATSPublisher(mock_js)

    job = _make_job()
    await publisher.publish_job(job)

    data = json.loads(mock_js.publish.call_args.args[1].decode())
    expected_keys = {"job_id", "project_id", "company_id", "source_file_id", "target_file_id", "mapping_file_id"}
    assert set(data.keys()) == expected_keys
