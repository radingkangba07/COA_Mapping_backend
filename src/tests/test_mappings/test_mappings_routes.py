"""Integration tests for mappings routes — T051."""

from typing import Any
from uuid import UUID

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
async def test_bulk_save_upserts(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    # First save — two INSERTs (no id)
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {"source_account_name": "A", "mapping_status": "suggested", "confidence_score": 50},
            {"source_account_name": "B", "mapping_status": "suggested", "confidence_score": 60},
        ],
    )
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    accounts = [a for g in list_resp.json() for a in g["accounts"]]
    assert len(accounts) == 2
    existing_id = accounts[0]["id"]

    # Second save — UPDATE one + INSERT one
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {"id": existing_id, "target_account_name": "Updated", "mapping_status": "approved"},
            {"source_account_name": "C", "mapping_status": "suggested", "confidence_score": 70},
        ],
    )
    body = resp.json()
    assert body["mapping_count"] == 2
    assert body["inserted"] == 1
    assert body["updated"] == 1

    # List should now have 3 total (original 2 + 1 new)
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    accounts = [a for g in list_resp.json() for a in g["accounts"]]
    assert len(accounts) == 3


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


async def _seed_suggestion(
    project_id: str,
    *,
    source_name: str = "Cash on Hand",
    source_type: str = "Asset",
    target_name: str = "Cash",
    target_type: str = "Asset",
    score: float = 90.0,
) -> str:
    """Insert a CoaMappingSuggestion directly and return its id."""
    from coa_db_models.mappings.models import CoaMappingSuggestion

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        suggestion = CoaMappingSuggestion(
            project_id=UUID(project_id),
            source_account_name=source_name,
            source_account_type=source_type,
            target_account_name=target_name,
            target_account_type=target_type,
            confidence_score=score,
            mapping_status="suggested",
            mapping_source="ml",
        )
        session.add(suggestion)
        await session.commit()
        await session.refresh(suggestion)
        return str(suggestion.id)
    return ""


@pytest.mark.asyncio
async def test_confirm_band_approves_confirmed_and_inserts_mapping(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id, source_name="High A", score=95)

    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}/confirm-band",
        json={"level": "high", "confirmed_suggestion_ids": [sugg_id], "deselected_suggestion_ids": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project_id
    assert data["level"] == "high"
    assert data["confirmed"] == 1
    assert data["inserted"] == 1
    assert data["reset"] == 0

    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    accounts = [a for g in list_resp.json() for a in g["accounts"]]
    mapping = next(a for a in accounts if a["source_name"] == "High A")
    assert mapping["status"] == "approved"


@pytest.mark.asyncio
async def test_confirm_band_resets_deselected_mapping_to_suggested(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id, source_name="High B", score=93)

    # First confirm it, then reset via deselected_suggestion_ids.
    await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}/confirm-band",
        json={"level": "high", "confirmed_suggestion_ids": [sugg_id], "deselected_suggestion_ids": []},
    )
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}/confirm-band",
        json={"level": "high", "confirmed_suggestion_ids": [], "deselected_suggestion_ids": [sugg_id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confirmed"] == 0
    assert data["reset"] == 1

    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    accounts = [a for g in list_resp.json() for a in g["accounts"]]
    mapping = next(a for a in accounts if a["source_name"] == "High B")
    assert mapping["status"] == "suggested"


@pytest.mark.asyncio
async def test_confirm_band_inserted_mapping_is_active_and_visible_via_suggestions(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    """Regression: a mapping newly INSERTED by confirm-band must be
    is_active=True — both list_by_project and the suggestions outer-join
    filter on is_active.is_(True), so an unset/NULL value silently hides the
    row from every subsequent fetch (looks like the confirm never happened
    once the page reloads or a new session loads the data)."""
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id, source_name="High C", score=96)

    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}/confirm-band",
        json={"level": "high", "confirmed_suggestion_ids": [sugg_id], "deselected_suggestion_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1

    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    accounts = [a for g in list_resp.json() for a in g["accounts"]]
    assert any(a["source_name"] == "High C" and a["status"] == "approved" for a in accounts)

    suggestions_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    rows = [a for g in suggestions_resp.json()["groups"] for a in g["accounts"]]
    row = next(a for a in rows if a["source_name"] == "High C")
    assert row["status"] == "approved"
    assert row["id"] is not None


@pytest.mark.asyncio
async def test_confirm_band_rejects_suggestion_from_other_project(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    other_project_id = await _create_project(authenticated_client, seed_user["org_id"])
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}/confirm-band",
        json={
            "level": "high",
            "confirmed_suggestion_ids": ["00000000-0000-0000-0000-000000000099"],
            "deselected_suggestion_ids": [],
        },
    )
    assert resp.status_code == 404
    assert other_project_id != project_id
