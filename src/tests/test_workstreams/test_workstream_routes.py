"""Integration tests for DAB-19 — Workstream CRUD + display code generation."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient, seed_user: dict[str, Any]) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "WS Test Project", "org_id": seed_user["org_id"]},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _get_category_id(client: AsyncClient, slug: str) -> str:
    """Seed the DB with a category and return its id via the workstream list response."""
    # Categories are seeded via Alembic migration. We fetch them by creating a
    # workstream and reading back the category_id, but for the first test we
    # need the id directly. Use the DB session via the app's override.
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from coa_db_models.workstreams.models import WorkstreamCategory
        from sqlalchemy import select

        result = await session.execute(
            select(WorkstreamCategory).where(WorkstreamCategory.slug == slug)
        )
        cat = result.scalar_one_or_none()
        if cat:
            return str(cat.id)
        # Not yet seeded — insert a fixture category
        cat = WorkstreamCategory(
            name="Master Data" if slug == "master_data" else "Opening Balances",
            slug=slug,
            display_code_prefix="MD" if slug == "master_data" else "OB",
            display_order=1 if slug == "master_data" else 2,
        )
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return str(cat.id)


@pytest.mark.asyncio
async def test_create_workstream(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user)
    category_id = await _get_category_id(authenticated_client, "master_data")

    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "Chart of Accounts"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Chart of Accounts"
    assert data["display_code"] == "MD-001"
    assert data["status"] == "not_started"
    assert data["category_name"] == "Master Data"
    assert data["project_id"] == project_id


@pytest.mark.asyncio
async def test_display_code_increments(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user)
    category_id = await _get_category_id(authenticated_client, "master_data")

    for name in ("First", "Second", "Third"):
        await authenticated_client.post(
            f"/api/v1/projects/{project_id}/workstreams",
            json={"category_id": category_id, "name": name},
        )

    resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/workstreams")
    codes = [w["display_code"] for w in resp.json()["workstreams"]]
    assert codes == ["MD-001", "MD-002", "MD-003"]


@pytest.mark.asyncio
async def test_display_code_per_category(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user)
    md_id = await _get_category_id(authenticated_client, "master_data")
    ob_id = await _get_category_id(authenticated_client, "opening_balances")

    await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": md_id, "name": "MD Workstream"},
    )
    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": ob_id, "name": "OB Workstream"},
    )
    assert resp.json()["display_code"] == "OB-001"


@pytest.mark.asyncio
async def test_list_workstreams(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user)
    category_id = await _get_category_id(authenticated_client, "master_data")

    await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "WS One"},
    )

    resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/workstreams")
    assert resp.status_code == 200
    body = resp.json()
    assert "workstreams" in body
    assert "total" in body
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_update_workstream(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user)
    category_id = await _get_category_id(authenticated_client, "master_data")

    create_resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "Original Name"},
    )
    ws_id = create_resp.json()["id"]

    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}/workstreams/{ws_id}",
        json={"name": "Renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["display_code"] == "MD-001"


@pytest.mark.asyncio
async def test_delete_workstream_with_stages_returns_409(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user)
    category_id = await _get_category_id(authenticated_client, "master_data")

    create_resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "Has Stages"},
    )
    ws_id = create_resp.json()["id"]

    # Default stages are auto-seeded on creation, so DELETE must return 409
    resp = await authenticated_client.delete(
        f"/api/v1/projects/{project_id}/workstreams/{ws_id}"
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_workstream_invalid_category(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user)
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await authenticated_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": fake_id, "name": "Bad Category"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_workstream_forbidden(test_client: AsyncClient, seed_user: dict[str, Any]):
    """A user with no project access cannot create workstreams."""
    # Create project as seed_user
    test_client.headers["Authorization"] = f"Bearer {seed_user['token']}"
    project_id = await _create_project(test_client, seed_user)
    category_id = await _get_category_id(test_client, "master_data")
    test_client.headers.pop("Authorization")

    # Register a second user with no project access
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Other User", "email": "other@example.com", "org_name": "Other Org"},
    )
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.core.security import create_access_token
        from src.modules.auth.repository import UserRepository

        repo = UserRepository(session)
        other = await repo.get_by_email("other@example.com")
        await repo.verify_user(other.id)
        await session.commit()
        other_token = create_access_token(data={"sub": str(other.id)})
        break

    resp = await test_client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "Forbidden"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403
