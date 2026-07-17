#!/usr/bin/env python3
"""Generate frontend/src/features/projects/data/erp-catalogue.data.ts from src/config/erp_systems.yaml.

Run from the repo root:
    python scripts/generate-erp-catalogue.py

Or with a custom output path:
    python scripts/generate-erp-catalogue.py --out ../COA_Mapping_frontend_V0/frontend/src/features/projects/data/erp-catalogue.data.ts
"""
import argparse
import json
import textwrap
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
YAML_PATH = REPO_ROOT / "src" / "config" / "erp_systems.yaml"
DEFAULT_OUT = (
    REPO_ROOT.parent
    / "COA_Mapping_frontend_V0"
    / "frontend"
    / "src"
    / "features"
    / "projects"
    / "data"
    / "erp-catalogue.data.ts"
)

RESERVED = {"vendors", "connection_methods"}


def build_catalogue(raw: dict) -> list[dict]:
    vendors: dict = raw.get("vendors", {})
    connection_methods: dict = raw.get("connection_methods", {})
    systems: dict = {k: v for k, v in raw.items() if k not in RESERVED}

    result = []
    for vendor_id, vendor in vendors.items():
        products = []
        for pid in vendor.get("products", []):
            system = systems.get(pid)
            if not system:
                continue
            methods = [
                {
                    "id": mid,
                    "name": connection_methods[mid]["name"],
                    "requires_mcp_config": connection_methods[mid].get("requires_mcp_config", False),
                }
                for mid in system.get("connection_methods", [])
                if mid in connection_methods
            ]
            products.append(
                {
                    "id": pid,
                    "product_name": system.get("name", pid),
                    "connection_methods": methods,
                }
            )
        result.append({"vendor": vendor.get("name", vendor_id), "products": products})
    return result


def to_ts(catalogue: list[dict]) -> str:
    data_json = json.dumps(catalogue, indent=2, ensure_ascii=False)
    # Indent the JSON block by 2 spaces so it sits neatly inside the `const` assignment
    indented = textwrap.indent(data_json, "  ")
    return f"""\
// AUTO-GENERATED — do not edit manually.
// Source: src/config/erp_systems.yaml in COA_Mapping_backend_V0
// Regenerate: python scripts/generate-erp-catalogue.py

export interface CatalogueConnectionMethod {{
  readonly id: string;
  readonly name: string;
  readonly requires_mcp_config: boolean;
}}

export interface CatalogueProduct {{
  readonly id: string;
  readonly product_name: string;
  readonly connection_methods: readonly CatalogueConnectionMethod[];
}}

export interface CatalogueVendor {{
  readonly vendor: string;
  readonly products: readonly CatalogueProduct[];
}}

export const ERP_CATALOGUE: readonly CatalogueVendor[] =
{indented} as const;
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ERP catalogue TypeScript constant.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output .ts file path")
    args = parser.parse_args()

    raw: dict = yaml.safe_load(YAML_PATH.read_text())
    catalogue = build_catalogue(raw)
    ts_content = to_ts(catalogue)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ts_content, encoding="utf-8")
    print(f"Written {len(catalogue)} vendors → {out_path}")


if __name__ == "__main__":
    main()
