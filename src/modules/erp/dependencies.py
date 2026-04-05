from functools import lru_cache
from pathlib import Path

from src.modules.erp.service import ERPConfigService

_BASE = Path(__file__).resolve().parent.parent.parent / "config"


@lru_cache
def get_erp_service() -> ERPConfigService:
    return ERPConfigService(
        systems_path=_BASE / "erp_systems.yaml",
    )
