"""Shared test fixtures for all modules."""

import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import Settings, get_settings
from src.core.database import Base, get_db
from src.main import app

# Test database URL — overridable via TEST_DATABASE_URL env var so CI and local
# devs can point at their own Postgres without editing this file. Default
# matches the credentials in .github/workflows/ci.yml so CI works out of the box.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://coa_user:coa_pass@localhost:5432/coa_migration_test",
)


def get_test_settings() -> Settings:
    """Return settings pointing at the test database."""
    return Settings(
        database_url=TEST_DATABASE_URL,
        jwt_secret="test-secret-key-for-testing-only",
        nats_url="",
        s3_endpoint="",
        debug=True,
    )


@pytest_asyncio.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client that spins up a fresh test DB and overrides dependencies."""
    settings = get_test_settings()
    test_engine = create_async_engine(settings.database_url, echo=False)

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = get_test_settings
    # Patch lru_cache so lifespan's get_settings() returns test settings
    get_settings.cache_clear()
    import src.core.config as config_module

    config_module.get_settings = get_test_settings  # type: ignore[assignment]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

    # Cleanup tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a standalone DB session for tests that manage their own client."""
    settings = get_test_settings()
    test_engine = create_async_engine(settings.database_url, echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def seed_user(test_client: AsyncClient) -> dict[str, Any]:
    """Login a test user (auto-creates via mock auth) and return user data."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"user_id": "testuser"},
    )
    return {"user_id": "testuser", "token": response.json()["token"]}


@pytest_asyncio.fixture
async def authenticated_client(
    test_client: AsyncClient, seed_user: dict[str, Any]
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with a valid mock Bearer token."""
    test_client.headers["Authorization"] = f"Bearer {seed_user['token']}"
    yield test_client
    test_client.headers.pop("Authorization", None)
