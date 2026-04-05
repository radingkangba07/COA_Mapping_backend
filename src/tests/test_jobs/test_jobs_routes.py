"""Integration tests for jobs routes — T085."""

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Jobs Test", "company_id": "jobs-co"},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_job_sync_fallback(authenticated_client: AsyncClient):
    project_id = await _create_project(authenticated_client)
    resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "completed"  # sync fallback
    assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_get_job(authenticated_client: AsyncClient):
    project_id = await _create_project(authenticated_client)
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


@pytest.mark.asyncio
async def test_get_job_status(authenticated_client: AsyncClient):
    project_id = await _create_project(authenticated_client)
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_complete"] is True
    assert data["has_error"] is False


@pytest.mark.asyncio
async def test_get_job_result(authenticated_client: AsyncClient):
    project_id = await _create_project(authenticated_client)
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}/result")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_list_project_jobs(authenticated_client: AsyncClient):
    project_id = await _create_project(authenticated_client)
    await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    resp = await authenticated_client.get(f"/api/v1/jobs/project/{project_id}")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_cancel_pending_job_fails_for_completed(authenticated_client: AsyncClient):
    """Sync fallback completes immediately, so cancel should fail."""
    project_id = await _create_project(authenticated_client)
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 404  # Not pending/queued — can't cancel
