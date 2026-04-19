"""Integration tests for projects routes — T039."""

from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project_auto_admin(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json={
            "name": "Test Project",
            "org_id": seed_user["org_id"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["status"] == "draft"
    project_id = data["id"]

    # Verify auto-admin access was granted
    access_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    assert access_resp.status_code == 200
    access_list = access_resp.json()
    assert len(access_list) >= 1
    assert any(a["permission"] == "admin" for a in access_list)


@pytest.mark.asyncio
async def test_create_project_default_erp(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "No ERP Project", "org_id": seed_user["org_id"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_system"] == ""
    assert data["target_system"] == ""


@pytest.mark.asyncio
async def test_list_projects(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "List Project", "org_id": seed_user["org_id"]},
    )
    resp = await authenticated_client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert "total" in data
    assert len(data["projects"]) >= 1


@pytest.mark.asyncio
async def test_get_project(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Get Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


@pytest.mark.asyncio
async def test_update_project(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Update Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_project(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Delete Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_dashboard(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Dashboard Project", "org_id": seed_user["org_id"]},
    )
    resp = await authenticated_client.get("/api/v1/dashboard/organizations")
    assert resp.status_code == 200
    data = resp.json()
    assert "organizations" in data
    assert "total_projects" in data
    assert len(data["organizations"]) >= 1
    assert all("projects" in org for org in data["organizations"])
