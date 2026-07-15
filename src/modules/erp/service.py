import time
from pathlib import Path
from typing import Any, cast

import yaml
from coa_db_models.erp.models import ErpCompatibilityRule
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_RESERVED = {"vendors", "connection_methods"}
_CACHE_TTL = 600  # seconds; applied to all ERP list responses (DAB-7)


class ERPConfigService:
    def __init__(self, systems_path: Path):
        raw: dict = yaml.safe_load(systems_path.read_text())
        self._vendors: dict = raw.get("vendors", {})
        self._connection_methods: dict = raw.get("connection_methods", {})
        self.systems: dict = {k: v for k, v in raw.items() if k not in _RESERVED}
        self._cache: dict[str, tuple[float, Any]] = {}

    def _get_cached(self, key: str, compute: Any) -> Any:
        entry = self._cache.get(key)
        if entry and time.monotonic() - entry[0] < _CACHE_TTL:
            return entry[1]
        result = compute()
        self._cache[key] = (time.monotonic(), result)
        return result

    # ── ERP products ──────────────────────────────────────────────────────────

    def get_all_systems(self) -> list[dict]:
        return [{"id": key, **value} for key, value in self.systems.items()]

    def get_products(self, vendor_id: str | None = None) -> list[dict]:
        """Return all products, optionally filtered by vendor. TTL-cached per filter key."""
        cache_key = f"erp:products:{vendor_id or 'all'}"
        if vendor_id:
            return cast(list[dict], self._get_cached(cache_key, lambda: self.get_products_for_vendor(vendor_id)))
        return cast(list[dict], self._get_cached(cache_key, self.get_all_systems))

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

    def search_vendors(self, q: str, max_results: int = 20) -> list[dict]:
        """Partial name match across vendors. TTL-cached per lowercase query string."""
        cache_key = f"erp:vendors:search:{q.lower()}"
        return cast(
            list[dict],
            self._get_cached(
                cache_key,
                lambda: [
                    {"id": key, **value}
                    for key, value in self._vendors.items()
                    if q.lower() in value.get("name", "").lower()
                ][:max_results],
            ),
        )

    # ── Connection methods ────────────────────────────────────────────────────

    def get_all_connection_methods(self) -> list[dict]:
        return cast(
            list[dict],
            self._get_cached(
                "erp:connection_methods",
                lambda: [{"id": key, **value} for key, value in self._connection_methods.items()],
            ),
        )

    def get_connection_method(self, connection_method_id: str) -> dict | None:
        if connection_method_id not in self._connection_methods:
            return None
        return {"id": connection_method_id, **self._connection_methods[connection_method_id]}

    def get_connection_methods_for_erp(self, erp_id: str) -> list[dict]:
        system = self.systems.get(erp_id)
        if not system:
            return []
        method_ids: list[str] = system.get("connection_methods", [])
        return [{"id": mid, **self._connection_methods[mid]} for mid in method_ids if mid in self._connection_methods]

    # ── Cascade helpers (vendor → product → method) ────────────────────────

    def get_catalogue_vendors(self) -> list[str]:
        """Unique vendor display names, ordered as defined in YAML."""
        return [v.get("name", k) for k, v in self._vendors.items()]

    def get_products_by_vendor_name(self, vendor_name: str) -> list[dict]:
        """Return products for a vendor matched by display name (case-insensitive)."""
        name_lower = vendor_name.lower()
        for vendor_id, vendor in self._vendors.items():
            if vendor.get("name", "").lower() == name_lower:
                return self.get_products_for_vendor(vendor_id)
        return []


async def check_compatibility_db(
    session: AsyncSession,
    source_product_id: str,
    target_product_id: str,
    connection_method_id: str,
) -> tuple[bool, str]:
    """Query erp_compatibility_rules for a specific product/method combination.

    Specific rules (with connection_method_id set) take precedence over general
    rules (connection_method_id IS NULL). Defaults to compatible when no rule matches.
    """
    specific = await session.execute(
        select(ErpCompatibilityRule).where(
            ErpCompatibilityRule.source_product_id == source_product_id,
            ErpCompatibilityRule.target_product_id == target_product_id,
            ErpCompatibilityRule.connection_method_id == connection_method_id,
        )
    )
    rule = specific.scalar_one_or_none()

    if rule is None:
        general = await session.execute(
            select(ErpCompatibilityRule).where(
                ErpCompatibilityRule.source_product_id == source_product_id,
                ErpCompatibilityRule.target_product_id == target_product_id,
                ErpCompatibilityRule.connection_method_id.is_(None),
            )
        )
        rule = general.scalar_one_or_none()

    if rule is None:
        return True, "Selected systems and connection methods are compatible for migration."
    if rule.is_compatible:
        return True, "Selected systems and connection methods are compatible for migration."
    return False, rule.incompatibility_reason or "The selected combination is not supported for migration."
