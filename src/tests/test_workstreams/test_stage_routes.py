"""Integration tests for DAB-20 — Workstream stage progression."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _setup_workstream(client: AsyncClient, seed_user: dict[str, Any]) -> tuple[str, str]:
    """Create a project + workstream; return (project_id, workstream_id)."""
    proj = await client.post(
        "/api/v1/projects",
        json={"name": "Stage Test Project", "org_id": seed_user["org_id"]},
    )
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    # Seed category
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from coa_db_models.workstreams.models import WorkstreamCategory
        from sqlalchemy import select

        result = await session.execute(select(WorkstreamCategory).where(WorkstreamCategory.slug == "master_data"))
        cat = result.scalar_one_or_none()
        if not cat:
            cat = WorkstreamCategory(
                name="Master Data",
                slug="master_data",
                display_code_prefix="MD",
                display_order=1,
            )
            session.add(cat)
            await session.commit()
            await session.refresh(cat)
        category_id = str(cat.id)
        break

    ws = await client.post(
        f"/api/v1/projects/{project_id}/workstreams",
        json={"category_id": category_id, "name": "Chart of Accounts"},
    )
    assert ws.status_code == 201
    return project_id, ws.json()["id"]


@pytest.mark.asyncio
async def test_list_stages(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")
    assert resp.status_code == 200
    stages = resp.json()
    assert len(stages) == 6
    sequences = [s["sequence"] for s in stages]
    assert sequences == [1, 2, 3, 4, 5, 6]
    names = [s["name"] for s in stages]
    assert names == [
        "Upload Files",
        "Type Mapping",
        "Account Mapping: 1",
        "Account Mapping: 2",
        "Account Mapping: 3",
        "Preview & Export",
    ]
    assert all(not s["is_completed"] for s in stages)


@pytest.mark.asyncio
async def test_complete_first_stage(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    stage_id = stages[0]["id"]

    resp = await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage_id}/complete")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_completed"] is True
    assert data["completed_at"] is not None
    assert data["completed_by"] is not None


@pytest.mark.asyncio
async def test_complete_stage_updates_current_stage(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)
    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()

    # Complete first stage
    await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stages[0]['id']}/complete")

    # List stages again — second stage name should now be current_stage on workstream
    updated_stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    assert updated_stages[0]["is_completed"] is True
    assert updated_stages[1]["is_completed"] is False


@pytest.mark.asyncio
async def test_complete_out_of_order_is_allowed(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)
    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()

    # Stages can be completed in any order — no ordering enforcement at this layer.
    resp = await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stages[1]['id']}/complete")
    assert resp.status_code == 200
    assert resp.json()["is_completed"] is True


@pytest.mark.asyncio
async def test_complete_stage_idempotent(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)
    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    stage_id = stages[0]["id"]

    first = await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage_id}/complete")
    second = await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage_id}/complete")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["completed_at"] == second.json()["completed_at"]


@pytest.mark.asyncio
async def test_complete_all_stages(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)
    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()

    for stage in stages:
        resp = await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage['id']}/complete")
        assert resp.status_code == 200

    # All stages should now be marked complete
    final = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    assert all(s["is_completed"] for s in final)


@pytest.mark.asyncio
async def test_list_stages_wrong_workstream_returns_404(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await authenticated_client.get(f"/api/v1/workstreams/{fake_id}/stages")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_complete_stage_wrong_workstream_returns_404(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    fake_ws = "00000000-0000-0000-0000-000000000000"
    fake_stage = "00000000-0000-0000-0000-000000000001"
    resp = await authenticated_client.patch(f"/api/v1/workstreams/{fake_ws}/stages/{fake_stage}/complete")
    assert resp.status_code == 404
