"""Service-level tests for email verification flow."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.email_service import EmailService
from src.modules.auth.repository import OrganizationRepository, UserRepository
from src.modules.auth.service import AuthService


@pytest.mark.asyncio
async def test_register_and_verify_flow(db_session: AsyncSession):
    user_repo = UserRepository(db_session)
    org_repo = OrganizationRepository(db_session)
    email_service = EmailService()
    service = AuthService(
        user_repo=user_repo,
        session=db_session,
        org_repo=org_repo,
        email_service=email_service,
    )

    # Register
    result = await service.register(name="Test", email="flow@example.com", org_name="Flow Org")
    assert result["message"] == "Verification email sent"

    # Check user has token and is not verified
    user = await user_repo.get_by_email("flow@example.com")
    assert user is not None
    assert user.verification_token is not None
    assert user.is_verified is False

    # Verify
    verify_result = await service.verify_email(user.verification_token)
    assert verify_result["success"] is True

    # Check user is now verified and token cleared
    await db_session.refresh(user)
    assert user.is_verified is True
    assert user.verification_token is None


@pytest.mark.asyncio
async def test_verify_token_reuse(db_session: AsyncSession):
    user_repo = UserRepository(db_session)
    org_repo = OrganizationRepository(db_session)
    service = AuthService(
        user_repo=user_repo,
        session=db_session,
        org_repo=org_repo,
        email_service=EmailService(),
    )

    # Register and get token
    await service.register(name="Reuse", email="reuse@example.com", org_name="Reuse Org")
    user = await user_repo.get_by_email("reuse@example.com")
    token = user.verification_token

    # First verify succeeds
    result1 = await service.verify_email(token)
    assert result1["success"] is True

    # Second verify fails (token cleared)
    result2 = await service.verify_email(token)
    assert result2["success"] is False
    assert "already used" in result2["error"]
