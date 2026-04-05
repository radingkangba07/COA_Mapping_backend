"""Unit tests for ERPConfigService."""

from pathlib import Path

import pytest

from src.modules.erp.service import ERPConfigService

SYSTEMS_PATH = Path(__file__).resolve().parents[2] / "config" / "erp_systems.yaml"


@pytest.fixture
def erp_service() -> ERPConfigService:
    return ERPConfigService(systems_path=SYSTEMS_PATH)


def test_loads_yaml(erp_service: ERPConfigService):
    assert erp_service.systems is not None


def test_returns_all_six_systems(erp_service: ERPConfigService):
    systems = erp_service.get_all_systems()
    assert len(systems) == 6
    ids = {s["id"] for s in systems}
    assert ids == {"sap", "oracle_netsuite", "microsoft_dynamics", "quickbooks", "sage", "xero"}


def test_get_system_returns_name(erp_service: ERPConfigService):
    sap = erp_service.get_system("sap")
    assert sap is not None
    assert sap["name"] == "SAP"


def test_get_system_unknown_returns_none(erp_service: ERPConfigService):
    assert erp_service.get_system("unknown_erp") is None


def test_account_types_returns_list(erp_service: ERPConfigService):
    types = erp_service.get_account_types("xero")
    assert isinstance(types, list)


def test_sample_data_returns_list(erp_service: ERPConfigService):
    data = erp_service.get_sample_data("quickbooks")
    assert isinstance(data, list)
