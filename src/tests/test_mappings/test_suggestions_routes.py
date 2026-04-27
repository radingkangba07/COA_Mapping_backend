"""Integration tests for the suggestion-aware mapping flow.

Covers:
- bulk save with suggestion_id (materialize + link)
- bulk save with {suggestion_id, is_active: false} (materialize-on-reject)
- delete_mapping soft-delete (is_active=false)
- suggestions GET state distinction (pending / confirmed / rejected)
- suggestions GET response shape (total + groups)
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient


async def _create_project(client: AsyncClient, org_id: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": "Suggestion Test Project", "org_id": org_id},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


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


def _flatten(groups: list[dict]) -> list[dict]:
    return [a for g in groups for a in g["accounts"]]


@pytest.mark.asyncio
async def test_suggestions_get_pending_returns_total_and_groups(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id)

    resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    rows = _flatten(body["groups"])
    assert len(rows) == 1
    assert rows[0]["suggestion_id"] == sugg_id
    # No mapping yet → id is null
    assert rows[0]["id"] is None


@pytest.mark.asyncio
async def test_bulk_save_via_suggestion_id_materializes_and_links(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id, source_name="Sales Revenue", source_type="Revenue")

    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"suggestion_id": sugg_id}],
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1
    assert resp.json()["updated"] == 0

    # GET suggestions → row now has a real mapping id (confirmed state)
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    rows = _flatten(list_resp.json()["groups"])
    assert len(rows) == 1
    assert rows[0]["suggestion_id"] == sugg_id
    assert rows[0]["id"] is not None

    # Re-sending the same suggestion_id now updates (idempotent)
    resp2 = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"suggestion_id": sugg_id, "target_account_name": "Revenue Updated"}],
    )
    assert resp2.json()["updated"] == 1
    assert resp2.json()["inserted"] == 0


@pytest.mark.asyncio
async def test_bulk_save_rejects_via_is_active_false(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id)

    # Reject the suggestion via the unified materialize pattern
    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"suggestion_id": sugg_id, "is_active": False}],
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1

    # Suggestion is now in "rejected" state — GET must hide it
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    body = list_resp.json()
    assert body["total"] == 0
    assert _flatten(body["groups"]) == []

    # Active mappings list also excludes it (is_active filter)
    mappings_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    assert _flatten(mappings_resp.json()) == []


@pytest.mark.asyncio
async def test_delete_mapping_soft_deletes_and_hides_from_lists(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    sugg_id = await _seed_suggestion(project_id)

    # Materialize the suggestion as a confirmed mapping
    save_resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[{"suggestion_id": sugg_id}],
    )
    assert save_resp.status_code == 201
    list_resp = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    mapping_id = _flatten(list_resp.json()["groups"])[0]["id"]
    assert mapping_id is not None

    # DELETE → soft-delete
    del_resp = await authenticated_client.delete(f"/api/v1/mappings/{mapping_id}")
    assert del_resp.status_code == 204

    # Both lists now exclude the row
    after_sugg = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}/suggestions")
    assert after_sugg.json()["total"] == 0
    after_map = await authenticated_client.get(f"/api/v1/mappings/project/{project_id}")
    assert _flatten(after_map.json()) == []

    # Verify is_active=false in DB (soft-delete, not hard delete)
    from coa_db_models.mappings.models import CoaMapping
    from sqlalchemy import select

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        row = (await session.execute(select(CoaMapping).where(CoaMapping.id == UUID(mapping_id)))).scalar_one()
        assert row.is_active is False
        break


@pytest.mark.asyncio
async def test_bulk_save_unknown_suggestion_id_falls_back_to_insert(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    """A suggestion_id that doesn't exist must not crash; backend treats it as a fresh insert."""
    project_id = await _create_project(authenticated_client, seed_user["org_id"])
    bogus_id = str(uuid4())

    resp = await authenticated_client.post(
        f"/api/v1/mappings/project/{project_id}",
        json=[
            {
                "suggestion_id": bogus_id,
                "source_account_name": "Manual Source",
                "mapping_status": "suggested",
                "confidence_score": 50.0,
            }
        ],
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 1
