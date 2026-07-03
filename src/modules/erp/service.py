from pathlib import Path
from typing import cast

import yaml

_RESERVED = {"vendors", "connection_methods"}


class ERPConfigService:
    def __init__(self, systems_path: Path):
        raw: dict = yaml.safe_load(systems_path.read_text())
        self._vendors: dict = raw.get("vendors", {})
        self._connection_methods: dict = raw.get("connection_methods", {})
        self.systems: dict = {k: v for k, v in raw.items() if k not in _RESERVED}

    # ── ERP products ──────────────────────────────────────────────────────────

    def get_all_systems(self) -> list[dict]:
        return [{"id": key, **value} for key, value in self.systems.items()]

    def get_system(self, erp_id: str) -> dict | None:
        if erp_id not in self.systems:
            return None
        return {"id": erp_id, **self.systems[erp_id]}

    def get_account_types(self, erp_id: str) -> list[str]:
        system = self.systems.get(erp_id)
        if not system:
            return []
        return cast(list[str], system.get("account_types", []))

    def get_sample_data(self, erp_id: str) -> list[dict]:
        system = self.systems.get(erp_id)
        if not system:
            return []
        return cast(list[dict], system.get("sample_data", []))

    # ── Vendors ───────────────────────────────────────────────────────────────

    def get_vendors(self) -> list[dict]:
        return [{"id": key, **value} for key, value in self._vendors.items()]

    def get_vendor(self, vendor_id: str) -> dict | None:
        if vendor_id not in self._vendors:
            return None
        return {"id": vendor_id, **self._vendors[vendor_id]}

    def get_products_for_vendor(self, vendor_id: str) -> list[dict]:
        vendor = self._vendors.get(vendor_id)
        if not vendor:
            return []
        product_ids: list[str] = vendor.get("products", [])
        return [{"id": pid, **self.systems[pid]} for pid in product_ids if pid in self.systems]

    # ── Connection methods ────────────────────────────────────────────────────

    def get_all_connection_methods(self) -> list[dict]:
        return [{"id": key, **value} for key, value in self._connection_methods.items()]

    def get_connection_methods_for_erp(self, erp_id: str) -> list[dict]:
        system = self.systems.get(erp_id)
        if not system:
            return []
        method_ids: list[str] = system.get("connection_methods", [])
        return [{"id": mid, **self._connection_methods[mid]} for mid in method_ids if mid in self._connection_methods]

    def get_connection_method(self, connection_method_id: str) -> dict | None:
        if connection_method_id not in self._connection_methods:
            return None
        return {"id": connection_method_id, **self._connection_methods[connection_method_id]}

    def check_compatibility(
        self,
        source_product_id: str,
        target_product_id: str,
        connection_method_id: str,
    ) -> tuple[bool, str]:
        source = self.systems.get(source_product_id)
        if not source:
            return False, f"Source product '{source_product_id}' not found"
        target = self.systems.get(target_product_id)
        if not target:
            return False, f"Target product '{target_product_id}' not found"
        if connection_method_id not in source.get("connection_methods", []):
            return False, f"Connection method '{connection_method_id}' is not supported by '{source['name']}'"
        return True, "Compatible"
