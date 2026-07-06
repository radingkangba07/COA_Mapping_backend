"""Tests for auth routes — magic link login + JWT auth."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from src.core.security import create_access_token

# --- Registration tests ---


@pytest.mark.asyncio
async def test_register_success(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Test User", "email": "test@example.com", "org_name": "Test Org"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "user_id" in data
    assert data["message"] == "Verification email sent"


@pytest.mark.asyncio
async def test_register_duplicate_email(test_client: AsyncClient):
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User A", "email": "dup@example.com", "org_name": "Org A"},
    )
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User B", "email": "dup@example.com", "org_name": "Org B"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_same_local_part_different_domain(test_client: AsyncClient):
    resp1 = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Anil A", "email": "anil@first.example", "org_name": "First Org"},
    )
    assert resp1.status_code == 201
    resp2 = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Anil B", "email": "anil@second.example", "org_name": "Second Org"},
    )
    assert resp2.status_code == 201


@pytest.mark.asyncio
async def test_register_duplicate_org(test_client: AsyncClient):
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User A", "email": "u1@example.com", "org_name": "Same Org"},
    )
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User B", "email": "u2@example.com", "org_name": "Same Org"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_missing_fields(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Test"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/auth/register",
        json={"name": "User", "email": "not-an-email", "org_name": "Org"},
    )
    assert resp.status_code == 422


# --- Email verification tests ---


@pytest.mark.asyncio
async def test_verify_email_invalid_token(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/auth/verify?token=invalid-garbage")
    assert resp.status_code == 200
    assert "Verification Failed" in resp.text


@pytest.mark.asyncio
async def test_verify_email_wrong_purpose(test_client: AsyncClient):
    token = create_access_token(
        data={"sub": "some-uuid", "purpose": "login"},
        expires_delta=timedelta(minutes=15),
    )
    resp = await test_client.get(f"/api/v1/auth/verify?token={token}")
    assert resp.status_code == 200
    assert "Verification Failed" in resp.text


@pytest.mark.asyncio
async def test_verify_missing_token_param(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/auth/verify")
    assert resp.status_code == 422


# --- Magic link login tests ---


async def _register_and_verify(client: AsyncClient, email: str, name: str = "Test", org: str = "Org") -> None:
    """Helper: register a user and verify them directly via DB."""
    await client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "org_name": org},
    )
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email(email)
        await user_repo.verify_user(user.id)
        await session.commit()


@pytest.mark.asyncio
async def test_login_verified_user(test_client: AsyncClient):
    await _register_and_verify(test_client, "login@example.com", org="Login Org")
    resp = await test_client.post("/api/v1/auth/login", json={"email": "login@example.com"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Magic link sent to your email"


@pytest.mark.asyncio
async def test_login_unverified_user(test_client: AsyncClient):
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Unverified", "email": "unverified@example.com", "org_name": "Unv Org"},
    )
    resp = await test_client.post("/api/v1/auth/login", json={"email": "unverified@example.com"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_login_unknown_email(test_client: AsyncClient):
    resp = await test_client.post("/api/v1/auth/login", json={"email": "nobody@example.com"})
    assert resp.status_code == 404


# --- Magic link verification tests ---


@pytest.mark.asyncio
async def test_magic_link_verify_success(test_client: AsyncClient):
    await _register_and_verify(test_client, "magic@example.com", org="Magic Org")
    # Request magic link
    await test_client.post("/api/v1/auth/login", json={"email": "magic@example.com"})

    # Get the magic link token from DB
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("magic@example.com")
        token = user.magic_link_token

    # Verify magic link
    resp = await test_client.get(f"/api/v1/auth/magic-link?token={token}")
    assert resp.status_code == 200
    # Should return HTML redirect page with tokens
    assert "Redirecting" in resp.text


@pytest.mark.asyncio
async def test_magic_link_reuse(test_client: AsyncClient):
    await _register_and_verify(test_client, "reuse@example.com", org="Reuse Org")
    await test_client.post("/api/v1/auth/login", json={"email": "reuse@example.com"})

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("reuse@example.com")
        token = user.magic_link_token

    # First use succeeds
    resp1 = await test_client.get(f"/api/v1/auth/magic-link?token={token}")
    assert resp1.status_code == 200
    assert "Redirecting" in resp1.text

    # Second use fails
    resp2 = await test_client.get(f"/api/v1/auth/magic-link?token={token}")
    assert resp2.status_code == 200
    assert "already used" in resp2.text.lower() or "invalid" in resp2.text.lower()


@pytest.mark.asyncio
async def test_magic_link_invalid_token(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/auth/magic-link?token=invalid-garbage")
    assert resp.status_code == 200
    assert "Failed" in resp.text or "invalid" in resp.text.lower()


# --- /me tests ---


@pytest.mark.asyncio
async def test_get_me_with_token(test_client: AsyncClient):
    await _register_and_verify(test_client, "me@example.com", name="Me User", org="Me Org")
    await test_client.post("/api/v1/auth/login", json={"email": "me@example.com"})

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("me@example.com")
        token = user.magic_link_token

    # Verify magic link to get tokens
    resp = await test_client.get(f"/api/v1/auth/magic-link?token={token}")
    assert resp.status_code == 200

    # Generate a valid access token for this user
    access_token = create_access_token(data={"sub": str(user.id)})
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "me@example.com"
    assert data["name"] == "Me User"
    assert data["is_verified"] is True
    assert len(data["orgs"]) == 1
    assert data["orgs"][0]["name"] == "Me Org"
    assert data["orgs"][0]["role"] == "owner"


@pytest.mark.asyncio
async def test_get_me_without_token(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(test_client: AsyncClient):
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 403


# --- Refresh tests ---


@pytest.mark.asyncio
async def test_refresh_tokens(test_client: AsyncClient):
    await _register_and_verify(test_client, "refresh@example.com", org="Refresh Org")
    await test_client.post("/api/v1/auth/login", json={"email": "refresh@example.com"})

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("refresh@example.com")
        magic_token = user.magic_link_token

    # Get tokens via magic link
    resp = await test_client.get(f"/api/v1/auth/magic-link?token={magic_token}")
    assert resp.status_code == 200

    # Extract refresh token from redirect URL
    import re

    match = re.search(r"refresh_token=([^&\"]+)", resp.text)
    assert match, "refresh_token not found in redirect"
    refresh_token = match.group(1)

    # Refresh
    resp = await test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_refresh_revoked_token(test_client: AsyncClient):
    await _register_and_verify(test_client, "revoked@example.com", org="Revoked Org")
    await test_client.post("/api/v1/auth/login", json={"email": "revoked@example.com"})

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("revoked@example.com")
        magic_token = user.magic_link_token

    resp = await test_client.get(f"/api/v1/auth/magic-link?token={magic_token}")
    import re

    match = re.search(r"refresh_token=([^&\"]+)", resp.text)
    refresh_token = match.group(1)

    # Refresh once (revokes old token)
    await test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    # Try to use old token again — should fail
    resp = await test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 403


# --- Logout tests ---


@pytest.mark.asyncio
async def test_logout(test_client: AsyncClient):
    await _register_and_verify(test_client, "logout@example.com", org="Logout Org")
    await test_client.post("/api/v1/auth/login", json={"email": "logout@example.com"})

    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("logout@example.com")
        magic_token = user.magic_link_token

    resp = await test_client.get(f"/api/v1/auth/magic-link?token={magic_token}")
    import re

    match = re.search(r"refresh_token=([^&\"]+)", resp.text)
    refresh_token = match.group(1)

    # Logout
    resp = await test_client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Logged out"

    # Refresh after logout should fail
    resp = await test_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 403
