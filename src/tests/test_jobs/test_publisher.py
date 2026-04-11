"""Unit tests for NATS job publisher payload structure."""

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.config import get_settings
from src.modules.jobs.publisher import NATSPublisher


def _make_job(**overrides) -> SimpleNamespace:
    defaults = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "job_type": "account_matching",
        "status": "queued",
        "progress": 0.0,
        "input_data": {
            "company_id": str(uuid.uuid4()),
            "source_system": "quickbooks",
            "target_system": "xero",
        },
        "source_file_id": uuid.uuid4(),
        "target_file_id": uuid.uuid4(),
        "mapping_file_id": uuid.uuid4(),
        "account_type_mapping_file_id": uuid.uuid4(),
        "triggered_by": uuid.uuid4(),
        "created_at": datetime.now(UTC),
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
    assert subject == get_settings().nats_subject_job_run

    data = json.loads(payload.decode())
    assert data["job_id"] == str(job.id)
    assert data["project_id"] == str(job.project_id)
    assert data["company_id"] == job.input_data["company_id"]
    assert data["job_type"] == "account_matching"
    assert data["source_file_id"] == str(job.source_file_id)
    assert data["target_file_id"] == str(job.target_file_id)
    assert data["mapping_file_id"] == str(job.mapping_file_id)
    assert data["account_type_mapping_file_id"] == str(job.account_type_mapping_file_id)
    assert data["triggered_by"] == str(job.triggered_by)
    assert data["created_at"] is not None
    assert data["event_at"] is not None
    assert data["metadata"]["source_system"] == "quickbooks"
    assert data["metadata"]["target_system"] == "xero"


@pytest.mark.asyncio
async def test_publish_job_no_file_ids():
    """File IDs are None when not set on the job."""
    mock_js = AsyncMock()
    publisher = NATSPublisher(mock_js)

    job = _make_job(
        source_file_id=None,
        target_file_id=None,
        mapping_file_id=None,
        account_type_mapping_file_id=None,
        triggered_by=None,
        input_data=None,
        created_at=None,
    )
    await publisher.publish_job(job)

    data = json.loads(mock_js.publish.call_args.args[1].decode())
    assert data["source_file_id"] is None
    assert data["target_file_id"] is None
    assert data["mapping_file_id"] is None
    assert data["account_type_mapping_file_id"] is None
    assert data["triggered_by"] is None
    assert data["company_id"] == ""


@pytest.mark.asyncio
async def test_publish_job_payload_keys():
    """Payload contains exactly the keys Bhavna's ML service expects."""
    mock_js = AsyncMock()
    publisher = NATSPublisher(mock_js)

    job = _make_job()
    await publisher.publish_job(job)

    data = json.loads(mock_js.publish.call_args.args[1].decode())
    expected_keys = {
        "job_id",
        "project_id",
        "company_id",
        "job_type",
        "source_file_id",
        "target_file_id",
        "mapping_file_id",
        "account_type_mapping_file_id",
        "triggered_by",
        "created_at",
        "event_at",
        "metadata",
    }
    assert set(data.keys()) == expected_keys
