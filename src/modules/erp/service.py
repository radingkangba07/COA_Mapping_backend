from pathlib import Path
from typing import cast

import yaml


class ERPConfigService:
    def __init__(self, systems_path: Path):
        self.systems: dict = yaml.safe_load(systems_path.read_text())

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
