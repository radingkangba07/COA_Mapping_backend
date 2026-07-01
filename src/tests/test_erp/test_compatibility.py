"""
Unit and integration tests for the ERP compatibility rules feature (DAB-1).

Covers:
- check_compatibility_db() — no rule (default compatible), specific rule,
  general rule, specific rule takes precedence, incompatible rule
- GET /api/v1/erp-systems/compatibility-check — valid query, incompatible
  result, missing params, in-memory TTL cache hit
"""

import uuid

import pytest
from coa_db_models import ErpCompatibilityRule
from httpx import AsyncClient

from src.modules.erp.service import check_compatibility_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule(
    source: str,
    target: str,
    method: str | None,
    is_compatible: bool,
    reason: str | None = None,
) -> ErpCompatibilityRule:
    return ErpCompatibilityRule(
        id=uuid.uuid4(),
        source_product_id=source,
        target_product_id=target,
        connection_method_id=method,
        is_compatible=is_compatible,
        incompatibility_reason=reason,
    )


# ---------------------------------------------------------------------------
# 1. check_compatibility_db() — service-level unit tests (hit real test DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_rule_defaults_to_compatible(test_client: AsyncClient):
    """When the table has no matching rule the function must return is_compatible=True."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        is_compatible, message = await check_compatibility_db(session, "sap", "oracle_netsuite", "csv_file")
        assert is_compatible is True
        assert "compatible" in message.lower()


@pytest.mark.asyncio
async def test_specific_rule_incompatible(test_client: AsyncClient):
    """A specific rule (with connection_method_id) marking incompatible must be returned."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        session.add(_rule("sap", "quickbooks", "on_premise", False, "On-premise not supported for this pair"))
        await session.flush()

        is_compatible, message = await check_compatibility_db(session, "sap", "quickbooks", "on_premise")
        assert is_compatible is False
        assert "on-premise" in message.lower()


@pytest.mark.asyncio
async def test_specific_rule_compatible(test_client: AsyncClient):
    """A specific rule marking compatible must return is_compatible=True."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        session.add(_rule("sap", "xero", "csv_file", True))
        await session.flush()

        is_compatible, message = await check_compatibility_db(session, "sap", "xero", "csv_file")
        assert is_compatible is True
        assert "compatible" in message.lower()


@pytest.mark.asyncio
async def test_general_rule_used_when_no_specific_rule(test_client: AsyncClient):
    """A general rule (connection_method_id IS NULL) must apply when no specific rule exists."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        session.add(_rule("sage", "zoho", None, False, "Sage to Zoho is not supported"))
        await session.flush()

        is_compatible, message = await check_compatibility_db(session, "sage", "zoho", "csv_file")
        assert is_compatible is False
        assert "zoho" in message.lower() or "not supported" in message.lower()


@pytest.mark.asyncio
async def test_specific_rule_takes_precedence_over_general(test_client: AsyncClient):
    """A specific rule must override a general rule for the same source/target pair."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        # General rule says incompatible
        session.add(_rule("odoo", "pastel", None, False, "Generally not supported"))
        # Specific rule for csv_file overrides and says compatible
        session.add(_rule("odoo", "pastel", "csv_file", True))
        await session.flush()

        is_compatible, _ = await check_compatibility_db(session, "odoo", "pastel", "csv_file")
        assert is_compatible is True


@pytest.mark.asyncio
async def test_incompatible_rule_without_reason_returns_fallback_message(test_client: AsyncClient):
    """An incompatible rule with no reason must return a sensible fallback message."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        session.add(_rule("microsoft_dynamics", "sap", "cloud_saas", False, None))
        await session.flush()

        is_compatible, message = await check_compatibility_db(session, "microsoft_dynamics", "sap", "cloud_saas")
        assert is_compatible is False
        assert len(message) > 0


# ---------------------------------------------------------------------------
# 2. GET /api/v1/erp-systems/compatibility-check — route integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compatibility_check_defaults_compatible(test_client: AsyncClient):
    """With no rule in the DB the endpoint must return is_compatible=true."""
    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "source_product_id": "sap",
            "target_product_id": "xero",
            "connection_method_id": "csv_file",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_compatible"] is True
    assert isinstance(data["message"], str)
    assert len(data["message"]) > 0


@pytest.mark.asyncio
async def test_compatibility_check_returns_incompatible_when_rule_exists(test_client: AsyncClient):
    """When a matching incompatible rule exists the endpoint must return is_compatible=false."""
    from src.core.database import get_db as _get_db
    from src.main import app

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        session.add(_rule("quickbooks", "sage", "on_premise", False, "QuickBooks does not support on-premise export"))
        await session.commit()

    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "source_product_id": "quickbooks",
            "target_product_id": "sage",
            "connection_method_id": "on_premise",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_compatible"] is False
    assert "on-premise" in data["message"].lower()


@pytest.mark.asyncio
async def test_compatibility_check_missing_source_returns_422(test_client: AsyncClient):
    """Omitting source_product_id must return 422."""
    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "target_product_id": "xero",
            "connection_method_id": "csv_file",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compatibility_check_missing_target_returns_422(test_client: AsyncClient):
    """Omitting target_product_id must return 422."""
    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "source_product_id": "sap",
            "connection_method_id": "csv_file",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compatibility_check_missing_method_returns_422(test_client: AsyncClient):
    """Omitting connection_method_id must return 422."""
    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "source_product_id": "sap",
            "target_product_id": "xero",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compatibility_check_response_shape(test_client: AsyncClient):
    """Response must always contain exactly is_compatible (bool) and message (str)."""
    resp = await test_client.get(
        "/api/v1/erp-systems/compatibility-check",
        params={
            "source_product_id": "sap",
            "target_product_id": "microsoft_dynamics",
            "connection_method_id": "csv_file",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"is_compatible", "message"}
    assert isinstance(data["is_compatible"], bool)
    assert isinstance(data["message"], str)


@pytest.mark.asyncio
async def test_compatibility_check_cache_hit_returns_same_result(test_client: AsyncClient):
    """Two identical requests must return the same result (cache hit on second call)."""
    params = {
        "source_product_id": "sap",
        "target_product_id": "oracle_netsuite",
        "connection_method_id": "csv_file",
    }
    resp1 = await test_client.get("/api/v1/erp-systems/compatibility-check", params=params)
    resp2 = await test_client.get("/api/v1/erp-systems/compatibility-check", params=params)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
