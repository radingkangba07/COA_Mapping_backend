"""Integration tests for mappings routes — T051."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient, org_id: str) -> str:
    """Helper to create a project and return its ID."""
    resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Mapping Test Project",
            "org_id": org_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_bulk_save_mappings(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    mappings = [
        {
            "source_account_name": "Sales Revenue",
            "source_account_number": "4000",
            "source_account_type": "Revenue",
            "target_account_name": "Revenue",
            "target_account_number": "400",
            "target_account_type": "Revenue",
            "confidence_score": 95.0,
            "mapping_status": "suggested",
        },
    ]
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=mappings,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["mapping_count"] == 1
    assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_bulk_save_replaces_existing(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    # First save
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"source_account_name": "Old", "mapping_status": "suggested", "confidence_score": 50}],
    )
    # Second save replaces
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {"source_account_name": "New1", "mapping_status": "suggested", "confidence_score": 80},
            {"source_account_name": "New2", "mapping_status": "suggested", "confidence_score": 90},
        ],
    )
    assert resp.json()["mapping_count"] == 2

    # List should only have the new ones (grouped format)
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    groups = list_resp.json()
    total_accounts = sum(len(g["accounts"]) for g in groups)
    assert total_accounts == 2


@pytest.mark.asyncio
async def test_list_mappings_with_filters(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {"source_account_name": "A", "mapping_status": "suggested", "confidence_score": 80},
            {"source_account_name": "B", "mapping_status": "approved", "confidence_score": 90},
        ],
    )
    resp = await authenticated_client.get(
        f"/api/v1/mappings/project/{project_id}",
        params={"status": "suggested"},
    )
    assert resp.status_code == 200
    groups = resp.json()
    # All accounts in grouped response should have the filtered status
    for group in groups:
        assert all(a["status"] == "suggested" for a in group["accounts"])


@pytest.mark.asyncio
async def test_mapping_stats(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {"source_account_name": "A", "mapping_status": "suggested", "confidence_score": 80},
            {"source_account_name": "B", "mapping_status": "approved", "confidence_score": 90},
        ],
    )
    resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["suggested"] >= 1


@pytest.mark.asyncio
async def test_export_mappings_excel(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"source_account_name": "Export", "mapping_status": "suggested", "confidence_score": 80}],
    )
    resp = await authenticated_client.post(f"/api/v1/mappings/project/{project_id}/export")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_fuzzy_match_endpoint(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/api/v1/mappings/fuzzy-match",
        json={
            "source_columns": ["Name", "Type"],
            "target_system": "xero",
            "threshold": 60,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "mappings" in data
    assert "target_fields" in data


@pytest.mark.asyncio
async def test_hierarchical_mapping_endpoint(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    resp = await authenticated_client.post(
        "/api/v1/mappings/hierarchical",
        json={
            "project_id": project_id,
            "source_file_id": "00000000-0000-0000-0000-000000000001",
            "target_file_id": "00000000-0000-0000-0000-000000000002",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["status"] == "queued"
    assert "job_id" in data
