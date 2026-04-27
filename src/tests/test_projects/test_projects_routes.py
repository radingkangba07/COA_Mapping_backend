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


# --- Access control: grant/update/revoke ---


async def _create_verified_user(test_client: AsyncClient, email: str, org_name: str = "Other Org") -> str:
    """Register + verify a second user; return user_id."""
    from src.core.database import get_db as _get_db
    from src.main import app
    from src.modules.auth.repository import UserRepository

    await test_client.post("/api/v1/auth/register", json={"name": email, "email": email, "org_name": org_name})
    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        await repo.verify_user(user.id)
        await session.commit()
        return str(user.id)
    return ""


@pytest.mark.asyncio
async def test_grant_access_to_self_returns_409(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Self Grant Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": seed_user["email"], "permission": "editor"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_grant_access_unknown_email_returns_404(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Unknown Email Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": "ghost@nowhere.test", "permission": "editor"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_grant_access_happy_path(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    other_email = "grantee@example.com"
    other_user_id = await _create_verified_user(test_client, other_email)
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Grant Happy Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]

    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": other_email, "permission": "editor"},
    )
    assert resp.status_code == 200
    list_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    assert any(a["user_id"] == other_user_id and a["permission"] == "editor" for a in list_resp.json())


@pytest.mark.asyncio
async def test_update_access_happy_path(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    other_email = "updatee@example.com"
    other_user_id = await _create_verified_user(test_client, other_email)
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Update Access Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": other_email, "permission": "viewer"},
    )

    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}/access/{other_user_id}",
        json={"permission": "approver"},
    )
    assert resp.status_code == 200
    list_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    assert any(a["user_id"] == other_user_id and a["permission"] == "approver" for a in list_resp.json())


@pytest.mark.asyncio
async def test_update_access_no_existing_returns_404(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    other_email = "noaccess@example.com"
    other_user_id = await _create_verified_user(test_client, other_email)
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "No Access Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}/access/{other_user_id}",
        json={"permission": "editor"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_access_self_returns_409(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json={"name": "Self Update Project", "org_id": seed_user["org_id"]},
    )
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}/access/{seed_user['user_id']}",
        json={"permission": "viewer"},
    )
    assert resp.status_code == 409
