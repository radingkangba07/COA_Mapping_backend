"""Integration tests for ERP routes — T061."""

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_list_erp_systems(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6


@pytest.mark.asyncio
async def test_get_single_system(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/sap")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "sap"
    assert data["name"] == "SAP"


@pytest.mark.asyncio
async def test_get_unknown_system_404(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/unknown")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_account_types(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/xero/account-types")
    assert resp.status_code == 200
    data = resp.json()
    assert data["erp_id"] == "xero"
    assert isinstance(data["account_types"], list)


@pytest.mark.asyncio
async def test_sample_data(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/quickbooks/sample-data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["erp_id"] == "quickbooks"
    assert isinstance(data["data"], list)
