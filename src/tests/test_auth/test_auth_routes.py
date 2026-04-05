"""Tests for auth routes — mock authentication."""

import pytest
from httpx import AsyncClient


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
