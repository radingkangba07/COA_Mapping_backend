"""Shared test fixtures for all modules."""

import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core import nats_client
from src.core.config import Settings, get_settings
from src.core.database import Base, get_db
from src.core.security import create_access_token
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

    # NATS is required in production but tests don't run a real server.
    # Inject a mock JetStream so get_jetstream() works and publish_job is a no-op.
    mock_js = MagicMock()
    mock_js.publish = AsyncMock()
    nats_client._js = mock_js

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    nats_client._js = None

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
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def seed_user(test_client: AsyncClient) -> dict[str, Any]:
    """Register, verify, and return a test user with a real JWT access token."""
    # Register
    await test_client.post(
        "/api/v1/auth/register",
        json={"name": "Test User", "email": "testuser@example.com", "org_name": "Test Org"},
    )

    # Get verification token from DB via verify endpoint
    # We need to directly create a verified user — use the service internals
    # Instead, we can get the user and generate a token directly
    from src.core.database import get_db as _get_db

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        from src.modules.auth.repository import UserRepository

        user_repo = UserRepository(session)
        user = await user_repo.get_by_email("testuser@example.com")

        # Verify user directly
        await user_repo.verify_user(user.id)
        await session.commit()
        await session.refresh(user)

        # Generate real JWT access token
        access_token = create_access_token(data={"sub": str(user.id)})

        # Get the org created during registration
        from src.modules.auth.repository import OrganizationRepository

        org_repo = OrganizationRepository(session)
        org = await org_repo.get_by_name("Test Org")

        return {
            "user_id": str(user.id),
            "token": access_token,
            "email": "testuser@example.com",
            "org_id": str(org.id) if org else None,
        }


@pytest_asyncio.fixture
async def authenticated_client(
    test_client: AsyncClient, seed_user: dict[str, Any]
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with a valid JWT Bearer token."""
    test_client.headers["Authorization"] = f"Bearer {seed_user['token']}"
    yield test_client
    test_client.headers.pop("Authorization", None)
