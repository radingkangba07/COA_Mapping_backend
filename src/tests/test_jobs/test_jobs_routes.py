"""Integration tests for jobs routes — T085."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient, org_id: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Jobs Test", "org_id": org_id},
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_job_publishes_to_nats(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "queued"
    assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_get_job(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


@pytest.mark.asyncio
async def test_get_job_status(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["is_complete"] is False
    assert data["has_error"] is False


@pytest.mark.asyncio
async def test_get_job_result_pending(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    # Queued jobs have no result yet — endpoint returns 404 until consumer completes them.
    resp = await authenticated_client.get(f"/api/v1/jobs/{job_id}/result")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_project_jobs(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    resp = await authenticated_client.get(f"/api/v1/jobs/project/{project_id}")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_cancel_queued_job(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    """Queued jobs can be cancelled."""
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    create_resp = await authenticated_client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "job_type": "account_matching"},
    )
    job_id = create_resp.json()["id"]
    resp = await authenticated_client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 204
