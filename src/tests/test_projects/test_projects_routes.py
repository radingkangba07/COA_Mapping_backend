"""Integration tests for projects routes — T039."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project_auto_admin(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json={
            "name": "Test Project",
            "company_id": "test-co",
            "company_name": "Test Company",
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
async def test_create_project_default_erp(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "No ERP Project", "company_id": "no-erp-co"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_system"] == ""
    assert data["target_system"] == ""


@pytest.mark.asyncio
async def test_list_projects(authenticated_client: AsyncClient):
    await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "List Project", "company_id": "list-co"},
    )
    resp = await authenticated_client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert "total" in data
    assert len(data["projects"]) >= 1


@pytest.mark.asyncio
async def test_get_project(authenticated_client: AsyncClient):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Get Project", "company_id": "get-co"},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


@pytest.mark.asyncio
async def test_update_project(authenticated_client: AsyncClient):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Update Project", "company_id": "update-co"},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_project(authenticated_client: AsyncClient):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Delete Project", "company_id": "delete-co"},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_create_company(authenticated_client: AsyncClient):
    resp = await authenticated_client.post(
        "/api/v1/companies",
        json={"slug": "new-company", "name": "New Company", "description": "A test company"},
    )
    assert resp.status_code == 201
    assert resp.json()["slug"] == "new-company"


@pytest.mark.asyncio
async def test_dashboard(authenticated_client: AsyncClient):
    # Create a project so dashboard has data
    await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Dashboard Project", "company_id": "dash-co", "company_name": "Dashboard Co"},
    )
    resp = await authenticated_client.get("/api/v1/dashboard/companies")
    assert resp.status_code == 200
    data = resp.json()
    assert "companies" in data
    assert "total_projects" in data
    assert len(data["companies"]) >= 1
    # Each company should have projects
    assert all("projects" in company for company in data["companies"])
