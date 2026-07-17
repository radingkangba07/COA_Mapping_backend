from pathlib import Path
from typing import cast

import yaml
from coa_db_models.erp.models import ErpCompatibilityRule
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_RESERVED = {"vendors", "connection_methods"}


class ERPConfigService:
    def __init__(self, systems_path: Path):
        raw: dict = yaml.safe_load(systems_path.read_text())
        self._connection_methods: dict = raw.get("connection_methods", {})
        self.systems: dict = {k: v for k, v in raw.items() if k not in _RESERVED}

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

    def get_connection_method(self, connection_method_id: str) -> dict | None:
        if connection_method_id not in self._connection_methods:
            return None
        return {"id": connection_method_id, **self._connection_methods[connection_method_id]}


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
