"""Integration tests for the org-membership / project-access boundary.

Project visibility is governed solely by `project_access`. Org membership
is required to be *granted* project access (see test_grant_access_non_org_member_returns_403
in test_projects_routes.py) but does not by itself confer visibility.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from src.core.database import get_db as _get_db
from src.core.security import create_access_token
from src.main import app


async def _verify_user(test_client: AsyncClient, email: str, org_name: str) -> str:
    await test_client.post("/api/v1/auth/register", json={"name": email, "email": email, "org_name": org_name})
    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        await repo.verify_user(user.id)
        await session.commit()
        return str(user.id)
    return ""


async def _add_org_member(user_id: str, org_id: str, role: str) -> None:
    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from uuid import UUID

        from src.modules.auth.repository import OrganizationRepository

        await OrganizationRepository(session).create_member(user_id=UUID(user_id), org_id=UUID(org_id), role=role)
        await session.commit()
        return


def _client_for(test_client: AsyncClient, user_id: str) -> AsyncClient:
    test_client.headers["Authorization"] = f"Bearer {create_access_token(data={'sub': user_id})}"
    return test_client


@pytest.mark.asyncio
async def test_org_member_without_explicit_grant_sees_no_projects(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    """Joining an org does not grant visibility on its projects — explicit access is required."""
    await authenticated_client.post("/api/v1/projects", json={"name": "Hidden Project", "org_id": seed_user["org_id"]})

    other_user_id = await _verify_user(test_client, "lurker@example.com", "Lurker Org")
    await _add_org_member(other_user_id, seed_user["org_id"], "member")

    _client_for(test_client, other_user_id)
    resp = await test_client.get("/api/v1/projects")
    assert resp.status_code == 200
    seed_org_projects = [p for p in resp.json()["projects"] if p["org_id"] == seed_user["org_id"]]
    assert seed_org_projects == []


@pytest.mark.asyncio
async def test_org_admin_without_explicit_grant_cannot_modify_project(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    """Even org admins need an explicit project_access row to operate on a project."""
    create_resp = await authenticated_client.post(
        "/api/v1/projects", json={"name": "Locked Project", "org_id": seed_user["org_id"]}
    )
    project_id = create_resp.json()["id"]

    admin_id = await _verify_user(test_client, "orgadmin@example.com", "Throwaway")
    await _add_org_member(admin_id, seed_user["org_id"], "admin")

    _client_for(test_client, admin_id)
    patch_resp = await test_client.patch(f"/api/v1/projects/{project_id}", json={"name": "Should Be Blocked"})
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_explicit_grant_after_org_invite_grants_visibility(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    create_resp = await authenticated_client.post(
        "/api/v1/projects", json={"name": "Shared Project", "org_id": seed_user["org_id"]}
    )
    project_id = create_resp.json()["id"]

    other_email = "collab@example.com"
    other_user_id = await _verify_user(test_client, other_email, "Throwaway")
    await _add_org_member(other_user_id, seed_user["org_id"], "member")
    grant_resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": other_email, "permission": "viewer"},
    )
    assert grant_resp.status_code == 200

    _client_for(test_client, other_user_id)
    resp = await test_client.get("/api/v1/projects")
    project = next((p for p in resp.json()["projects"] if p["id"] == project_id), None)
    assert project is not None
    assert project["effective_permission"] == "viewer"


@pytest.mark.asyncio
async def test_org_id_query_param_scopes_results(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    p_in_seed = await authenticated_client.post(
        "/api/v1/projects", json={"name": "Seed Org Project", "org_id": seed_user["org_id"]}
    )
    p_in_seed_id = p_in_seed.json()["id"]

    second_user_id = await _verify_user(test_client, "owner2@example.com", "Second Org")
    second_org_id: str | None = None
    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import OrganizationRepository

        second_org = await OrganizationRepository(session).get_by_name("Second Org")
        second_org_id = str(second_org.id)
        break
    assert second_org_id is not None

    _client_for(test_client, second_user_id)
    p_in_second = await test_client.post(
        "/api/v1/projects", json={"name": "Second Org Project", "org_id": second_org_id}
    )
    p_in_second_id = p_in_second.json()["id"]

    await _add_org_member(second_user_id, seed_user["org_id"], "member")
    _client_for(test_client, seed_user["user_id"])
    grant_resp = await test_client.post(
        f"/api/v1/projects/{p_in_seed_id}/access",
        json={"email": "owner2@example.com", "permission": "viewer"},
    )
    assert grant_resp.status_code == 200

    _client_for(test_client, second_user_id)
    resp_seed = await test_client.get(f"/api/v1/projects?org_id={seed_user['org_id']}")
    seed_ids = {p["id"] for p in resp_seed.json()["projects"]}
    assert seed_ids == {p_in_seed_id}

    resp_second = await test_client.get(f"/api/v1/projects?org_id={second_org_id}")
    second_ids = {p["id"] for p in resp_second.json()["projects"]}
    assert second_ids == {p_in_second_id}


@pytest.mark.asyncio
async def test_non_member_cannot_be_granted_access(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    """Even with the right project_access endpoint, a non-org-member cannot be added."""
    create_resp = await authenticated_client.post(
        "/api/v1/projects", json={"name": "Org-only Project", "org_id": seed_user["org_id"]}
    )
    project_id = create_resp.json()["id"]

    outsider_email = "stranger@example.com"
    await _verify_user(test_client, outsider_email, "Stranger Org")

    grant_resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": outsider_email, "permission": "viewer"},
    )
    assert grant_resp.status_code == 403
