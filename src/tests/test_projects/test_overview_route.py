"""Integration tests for DAB-18 — GET /api/v1/projects/{id}/overview."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient, seed_user: dict[str, Any], **kwargs) -> dict:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Overview Project", "org_id": seed_user["org_id"], **kwargs},
    )
    assert resp.status_code == 201
    return resp.json()


async def _seed_category(seed_user: dict[str, Any]) -> str:
    """Return a WorkstreamCategory id, creating it if needed."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from coa_db_models.workstreams.models import WorkstreamCategory
        from sqlalchemy import select

        result = await session.execute(select(WorkstreamCategory).where(WorkstreamCategory.slug == "overview_test"))
        cat = result.scalar_one_or_none()
        if not cat:
            cat = WorkstreamCategory(
                name="Overview Test",
                slug="overview_test",
                display_code_prefix="OT",
                display_order=99,
            )
            session.add(cat)
            await session.commit()
            await session.refresh(cat)
        return str(cat.id)


@pytest.mark.asyncio
async def test_overview_no_workstreams(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(
        authenticated_client,
        seed_user,
        source_system="SAP",
        target_system="Odoo",
    )
    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == project["id"]
    assert data["name"] == "Overview Project"
    assert data["source_erp"] == "SAP"
    assert data["target_erp"] == "Odoo"
    assert data["source_deployment"] is None
    assert data["target_deployment"] is None
    assert data["groups"] == []
    assert "last_edited_at" in data


@pytest.mark.asyncio
async def test_overview_with_workstreams(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(authenticated_client, seed_user)
    category_id = await _seed_category(seed_user)

    # Create two workstreams
    ws1 = await authenticated_client.post(
        f"/api/v1/projects/{project['id']}/workstreams",
        json={"category_id": category_id, "name": "COA Migration"},
    )
    ws2 = await authenticated_client.post(
        f"/api/v1/projects/{project['id']}/workstreams",
        json={"category_id": category_id, "name": "Vendor Migration"},
    )
    assert ws1.status_code == 201
    assert ws2.status_code == 201

    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["groups"]) == 1
    group = data["groups"][0]
    assert group["key"] == "overview_test"
    assert group["title"] == "Overview Test"
    assert len(group["workstreams"]) == 2

    for ws in group["workstreams"]:
        assert "id" in ws
        assert "code" in ws
        assert "name" in ws
        assert "status" in ws
        assert "progress" in ws
        assert "current_stage" in ws
        assert ws["included"] is True


@pytest.mark.asyncio
async def test_overview_progress_zero_on_fresh_workstream(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(authenticated_client, seed_user)
    category_id = await _seed_category(seed_user)

    await authenticated_client.post(
        f"/api/v1/projects/{project['id']}/workstreams",
        json={"category_id": category_id, "name": "Fresh WS"},
    )

    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    ws = resp.json()["groups"][0]["workstreams"][0]
    assert ws["progress"] == 0
    assert ws["status"] == "not_started"


@pytest.mark.asyncio
async def test_overview_progress_updates_after_stages_completed(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project = await _create_project(authenticated_client, seed_user)
    category_id = await _seed_category(seed_user)

    ws_resp = await authenticated_client.post(
        f"/api/v1/projects/{project['id']}/workstreams",
        json={"category_id": category_id, "name": "Stage WS"},
    )
    ws_id = ws_resp.json()["id"]

    # Complete 2 of 4 stages
    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    for stage in stages[:2]:
        await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage['id']}/complete")

    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    ws = resp.json()["groups"][0]["workstreams"][0]
    assert ws["progress"] == 50


@pytest.mark.asyncio
async def test_overview_progress_100_when_all_stages_done(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(authenticated_client, seed_user)
    category_id = await _seed_category(seed_user)

    ws_resp = await authenticated_client.post(
        f"/api/v1/projects/{project['id']}/workstreams",
        json={"category_id": category_id, "name": "Complete WS"},
    )
    ws_id = ws_resp.json()["id"]

    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    for stage in stages:
        await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage['id']}/complete")

    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    ws = resp.json()["groups"][0]["workstreams"][0]
    assert ws["progress"] == 100


@pytest.mark.asyncio
async def test_overview_project_code_field(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(authenticated_client, seed_user)
    resp = await authenticated_client.get(f"/api/v1/projects/{project['id']}/overview")
    assert resp.status_code == 200
    data = resp.json()
    # project_code maps to display_code which may be None for a fresh project
    assert "project_code" in data


@pytest.mark.asyncio
async def test_overview_requires_auth(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project = await _create_project(authenticated_client, seed_user)

    from httpx import ASGITransport
    from httpx import AsyncClient as RawClient

    from src.main import app

    async with RawClient(transport=ASGITransport(app=app), base_url="http://test") as anon_client:
        resp = await anon_client.get(f"/api/v1/projects/{project['id']}/overview")
        assert resp.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_overview_not_found(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await authenticated_client.get(f"/api/v1/projects/{fake_id}/overview")
    assert resp.status_code in (403, 404)
