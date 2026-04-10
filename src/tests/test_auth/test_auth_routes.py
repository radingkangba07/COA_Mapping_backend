"""Tests for auth routes — mock authentication."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from src.core.security import create_access_token


@pytest.mark.asyncio
async def test_login_creates_new_user(test_client: AsyncClient):
    resp = await test_client.post(
        "/api/v1/auth/login",
        json={"user_id": "newuser"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_new_user"] is True
    assert data["token"] == "mock-token-newuser"
    assert data["user"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_login_existing_user(test_client: AsyncClient):
    await test_client.post("/api/v1/auth/login", json={"user_id": "returning"})
    resp = await test_client.post("/api/v1/auth/login", json={"user_id": "returning"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_new_user"] is False


@pytest.mark.asyncio
async def test_get_me_with_token(test_client: AsyncClient):
    login_resp = await test_client.post("/api/v1/auth/login", json={"user_id": "meuser"})
    token = login_resp.json()["token"]
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "meuser@example.com"


@pytest.mark.asyncio
async def test_get_me_without_token(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/auth/me")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_me_invalid_token(test_client: AsyncClient):
    resp = await test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_logout(test_client: AsyncClient):
    resp = await test_client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


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
