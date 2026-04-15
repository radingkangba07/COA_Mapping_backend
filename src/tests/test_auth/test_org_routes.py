"""Tests for organization member and invitation routes."""

import uuid

import pytest
from httpx import AsyncClient

from src.core.security import create_access_token

# --- GET /api/v1/orgs/{org_id}/members ---


@pytest.mark.asyncio
async def test_get_org_members_success(authenticated_client: AsyncClient, seed_user: dict):
    """Owner can list org members."""
    # Get user's org id
    resp = await authenticated_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    org_id = resp.json()["orgs"][0]["id"]

    resp = await authenticated_client.get(f"/api/v1/orgs/{org_id}/members")
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) == 1
    assert members[0]["email"] == seed_user["email"]
    assert members[0]["role"] == "owner"
    assert members[0]["name"] == "Test User"
    assert "joined_at" in members[0]
    assert "user_id" in members[0]


@pytest.mark.asyncio
async def test_get_org_members_not_found(authenticated_client: AsyncClient):
    """Returns 404 for non-existent org."""
    fake_id = str(uuid.uuid4())
    resp = await authenticated_client.get(f"/api/v1/orgs/{fake_id}/members")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_org_members_not_a_member(test_client: AsyncClient):
    """Returns 403 when user is not a member of the org."""
    # Register two users with separate orgs
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User A", "email": "usera@example.com", "org_name": "Org A"},
    )
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User B", "email": "userb@example.com", "org_name": "Org B"},
    )

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import OrganizationRepository, UserRepository

        user_repo = UserRepository(session)
        org_repo = OrganizationRepository(session)

        user_a = await user_repo.get_by_email("usera@example.com")
        await user_repo.verify_user(user_a.id)

        # Get Org B's id (user A is NOT a member)
        org_b = await org_repo.get_by_name("Org B")

        await session.commit()

    token_a = create_access_token(data={"sub": str(user_a.id)})
    resp = await test_client.get(
        f"/api/v1/orgs/{org_b.id}/members",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_org_members_unauthenticated(test_client: AsyncClient):
    """Returns 422 when no auth header provided."""
    fake_id = str(uuid.uuid4())
    resp = await test_client.get(f"/api/v1/orgs/{fake_id}/members")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_org_members_invalid_token(test_client: AsyncClient):
    """Returns 403 with invalid bearer token."""
    fake_id = str(uuid.uuid4())
    resp = await test_client.get(
        f"/api/v1/orgs/{fake_id}/members",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_org_members_multiple(test_client: AsyncClient):
    """Returns all members when org has multiple members."""
    # Register user A with org
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Owner", "email": "owner@example.com", "org_name": "Multi Org"},
    )

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import OrganizationRepository, UserRepository

        user_repo = UserRepository(session)
        org_repo = OrganizationRepository(session)

        owner = await user_repo.get_by_email("owner@example.com")
        await user_repo.verify_user(owner.id)

        org = await org_repo.get_by_name("Multi Org")

        # Add a second member directly
        second_user = await user_repo.create_user(user_id="member2", email="member2@example.com", name="Member Two")
        await org_repo.create_member(user_id=second_user.id, org_id=org.id, role="member")

        await session.commit()

    token = create_access_token(data={"sub": str(owner.id)})
    resp = await test_client.get(
        f"/api/v1/orgs/{org.id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) == 2
    emails = {m["email"] for m in members}
    assert emails == {"owner@example.com", "member2@example.com"}


# --- GET /api/v1/orgs/{org_id}/invitations ---


@pytest.mark.asyncio
async def test_get_org_invitations_returns_empty(authenticated_client: AsyncClient, seed_user: dict):
    """Invitations endpoint returns empty list (no invitation model yet)."""
    resp = await authenticated_client.get("/api/v1/auth/me")
    org_id = resp.json()["orgs"][0]["id"]

    resp = await authenticated_client.get(f"/api/v1/orgs/{org_id}/invitations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_org_invitations_unauthenticated(test_client: AsyncClient):
    """Returns 422 when no auth header provided."""
    fake_id = str(uuid.uuid4())
    resp = await test_client.get(f"/api/v1/orgs/{fake_id}/invitations")
    assert resp.status_code == 422
