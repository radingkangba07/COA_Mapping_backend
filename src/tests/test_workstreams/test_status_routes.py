"""Integration tests for DAB-21 — Workstream status transition and log."""

from typing import Any

import pytest
from httpx import AsyncClient


async def _setup_workstream(client: AsyncClient, seed_user: dict[str, Any]) -> tuple[str, str]:
    """Create a project + workstream; return (project_id, workstream_id)."""
    proj = await client.post(
        "/api/v1/projects",
        json={"name": "Status Test Project", "org_id": seed_user["org_id"]},
    )
    assert proj.status_code == 201
    project_id = proj.json()["id"]

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
async def test_transition_status(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "in_progress", "note": "Starting migration"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["previous_status"] == "not_started"
    assert data["new_status"] == "in_progress"
    assert data["note"] == "Starting migration"
    assert data["changed_by"] is not None
    assert data["workstream_id"] == ws_id


@pytest.mark.asyncio
async def test_transition_status_no_note(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "blocked"},
    )
    assert resp.status_code == 201
    assert resp.json()["note"] is None


@pytest.mark.asyncio
async def test_transition_same_status_returns_422(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "not_started"},
    )
    assert resp.status_code == 422
    assert "already in this status" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transition_invalid_status_returns_422(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "flying"},
    )
    assert resp.status_code == 422
    assert "Invalid status" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transition_to_completed_with_incomplete_stages_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "completed"},
    )
    assert resp.status_code == 422
    assert "All stages must be completed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transition_to_completed_after_all_stages_done(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    stages = (await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/stages")).json()
    for stage in stages:
        await authenticated_client.patch(f"/api/v1/workstreams/{ws_id}/stages/{stage['id']}/complete")

    resp = await authenticated_client.post(
        f"/api/v1/workstreams/{ws_id}/status",
        json={"new_status": "completed"},
    )
    assert resp.status_code == 201
    assert resp.json()["new_status"] == "completed"


@pytest.mark.asyncio
async def test_list_status_log_empty(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    resp = await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/status-log")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_status_log_ordered_newest_first(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    _, ws_id = await _setup_workstream(authenticated_client, seed_user)

    await authenticated_client.post(f"/api/v1/workstreams/{ws_id}/status", json={"new_status": "in_progress"})
    await authenticated_client.post(f"/api/v1/workstreams/{ws_id}/status", json={"new_status": "review_required"})

    resp = await authenticated_client.get(f"/api/v1/workstreams/{ws_id}/status-log")
    assert resp.status_code == 200
    log = resp.json()
    assert len(log) == 2
    assert log[0]["new_status"] == "review_required"
    assert log[1]["new_status"] == "in_progress"


@pytest.mark.asyncio
async def test_status_log_wrong_workstream_returns_404(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await authenticated_client.get(f"/api/v1/workstreams/{fake_id}/status-log")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transition_wrong_workstream_returns_404(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await authenticated_client.post(f"/api/v1/workstreams/{fake_id}/status", json={"new_status": "in_progress"})
    assert resp.status_code == 404
