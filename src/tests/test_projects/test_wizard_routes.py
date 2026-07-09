"""Tests for DAB-9: POST /api/v1/projects full atomic creation (wizard flow).

Covers:
- draft creation (minimal and partial ERP config)
- create action (valid and invalid ERP combinations)
- ERP validation (unknown vendor, product, incompatible connection method)
- MCP server guard (requires mcp_connection_config on create)
- Master data and opening balance persistence
- Member assignment at creation time
- GET project field checks and access enforcement
- List projects pagination and org filter
- PATCH / DELETE permission guards
- Unauthenticated request rejection (401)
- ERP catalogue endpoints used by the wizard Step 1 UI
"""

from typing import Any
from uuid import UUID

from httpx import AsyncClient


def _draft_payload(org_id: str, **overrides) -> dict:
    return {"name": "Wizard Project", "org_id": org_id, "action": "draft", **overrides}


def _create_payload(org_id: str, **overrides) -> dict:
    base = {
        "name": "Full Wizard Project",
        "org_id": org_id,
        "action": "create",
        "source_vendor_id": "sap",
        "source_product_id": "sap",
        "source_connection_method_id": "csv_file",
        "target_vendor_id": "microsoft",
        "target_product_id": "microsoft_dynamics",
        "target_connection_method_id": "csv_file",
    }
    base.update(overrides)
    return base


async def _register_and_verify(test_client: AsyncClient, email: str, org_name: str) -> str:
    from src.core.database import get_db as _get_db
    from src.main import app
    from src.modules.auth.repository import UserRepository

    await test_client.post(
        "/api/v1/auth/register",
        json={"name": email, "email": email, "org_name": org_name},
    )
    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        await repo.verify_user(user.id)
        await session.commit()
        return str(user.id)
    return ""


async def _add_to_org(user_id: str, org_id: str) -> None:
    from src.core.database import get_db as _get_db
    from src.main import app
    from src.modules.auth.repository import OrganizationRepository

    db_override = app.dependency_overrides.get(_get_db)
    async for session in db_override():
        await OrganizationRepository(session).create_member(user_id=UUID(user_id), org_id=UUID(org_id), role="member")
        await session.commit()
        return


async def _get_token_for(user_id: str) -> str:
    from src.core.security import create_access_token

    return create_access_token(data={"sub": user_id})


# ---------------------------------------------------------------------------
# 1. Draft creation
# ---------------------------------------------------------------------------


async def test_wizard_draft_minimal(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["name"] == "Wizard Project"


async def test_wizard_draft_with_partial_erp_config(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_draft_payload(seed_user["org_id"], source_vendor_id="sap", source_product_id="sap"),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "draft"


async def test_wizard_draft_creator_is_auto_admin(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = resp.json()["id"]

    access_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    assert access_resp.status_code == 200
    assert any(a["permission"] == "admin" for a in access_resp.json())


# ---------------------------------------------------------------------------
# 2. Full create (action=create)
# ---------------------------------------------------------------------------


async def test_wizard_create_valid_erp_combo_returns_active(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    resp = await authenticated_client.post("/api/v1/projects", json=_create_payload(seed_user["org_id"]))
    assert resp.status_code == 201
    assert resp.json()["status"] == "active"


async def test_wizard_create_without_vendor_ids_succeeds(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    # vendor IDs are auto-derived from product IDs — omitting them is valid
    payload = _create_payload(seed_user["org_id"])
    payload.pop("source_vendor_id", None)
    payload.pop("target_vendor_id", None)
    resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 201


async def test_wizard_create_missing_source_product_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    payload = _create_payload(seed_user["org_id"])
    del payload["source_product_id"]
    resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 422


async def test_wizard_create_missing_connection_method_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    payload = _create_payload(seed_user["org_id"])
    del payload["source_connection_method_id"]
    resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 422


async def test_wizard_create_missing_all_target_fields_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    payload = _create_payload(seed_user["org_id"])
    del payload["target_vendor_id"]
    del payload["target_product_id"]
    del payload["target_connection_method_id"]
    resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. ERP validation
# ---------------------------------------------------------------------------


async def test_wizard_create_unknown_source_vendor_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_create_payload(seed_user["org_id"], source_vendor_id="nonexistent_vendor"),
    )
    assert resp.status_code == 422


async def test_wizard_create_unknown_target_vendor_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_create_payload(seed_user["org_id"], target_vendor_id="nonexistent_vendor"),
    )
    assert resp.status_code == 422


async def test_wizard_create_unknown_source_product_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_create_payload(seed_user["org_id"], source_product_id="nonexistent_product"),
    )
    assert resp.status_code == 422


async def test_wizard_create_incompatible_connection_method_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    """SAP does not support cloud_saas — the compatibility check must reject with 422."""
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_create_payload(
            seed_user["org_id"],
            source_vendor_id="sap",
            source_product_id="sap",
            source_connection_method_id="cloud_saas",
        ),
    )
    assert resp.status_code == 422


async def test_wizard_create_mcp_server_without_config_returns_422(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    """mcp_server connection method requires mcp_connection_config on action=create."""
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_create_payload(
            seed_user["org_id"],
            source_vendor_id="sap",
            source_product_id="sap",
            source_connection_method_id="mcp_server",
        ),
    )
    assert resp.status_code == 422


async def test_wizard_mcp_server_rejected_even_for_draft(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    """mcp_server must be rejected at schema level regardless of action."""
    resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_draft_payload(seed_user["org_id"], source_connection_method_id="mcp_server"),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Migration scope persistence
# ---------------------------------------------------------------------------


async def test_wizard_create_master_data_scope_is_stored(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    payload = _draft_payload(
        seed_user["org_id"],
        master_data_selections=[
            {"data_type": "chart_of_accounts", "selected": True},
            {"data_type": "vendors", "selected": True},
            {"data_type": "customers", "selected": False},
        ],
    )
    create_resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201

    project_id = create_resp.json()["id"]
    get_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200

    selections = get_resp.json().get("master_data_selections") or []
    stored_types = [item["data_type"] for item in selections]
    assert "chart_of_accounts" in stored_types
    assert "vendors" in stored_types


async def test_wizard_create_opening_balance_scope_is_stored(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    payload = _draft_payload(
        seed_user["org_id"],
        opening_balance_selections=[
            {"account_type": "trial_balance", "include": True},
            {"account_type": "accounts_receivable", "include": True},
        ],
    )
    create_resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201

    project_id = create_resp.json()["id"]
    get_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}")
    selections = get_resp.json().get("opening_balance_selections") or []
    stored_types = [item["account_type"] for item in selections]
    assert "trial_balance" in stored_types
    assert "accounts_receivable" in stored_types


# ---------------------------------------------------------------------------
# 5. Members at creation
# ---------------------------------------------------------------------------


async def test_wizard_create_with_members_grants_access(
    authenticated_client: AsyncClient,
    test_client: AsyncClient,
    seed_user: dict[str, Any],
):
    member_email = "wizard_member@example.com"
    member_id = await _register_and_verify(test_client, member_email, "WM Org")
    await _add_to_org(member_id, seed_user["org_id"])

    payload = _draft_payload(
        seed_user["org_id"],
        members=[{"email": member_email, "permission": "editor"}],
    )
    create_resp = await authenticated_client.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    access_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    assert access_resp.status_code == 200
    assert any(a["user_id"] == member_id and a["permission"] == "editor" for a in access_resp.json())


async def test_wizard_create_creator_always_admin_regardless_of_members(
    authenticated_client: AsyncClient,
    test_client: AsyncClient,
    seed_user: dict[str, Any],
):
    member_email = "member_admin_check@example.com"
    member_id = await _register_and_verify(test_client, member_email, "MAC Org")
    await _add_to_org(member_id, seed_user["org_id"])

    payload = _draft_payload(
        seed_user["org_id"],
        members=[{"email": member_email, "permission": "viewer"}],
    )
    create_resp = await authenticated_client.post("/api/v1/projects", json=payload)
    project_id = create_resp.json()["id"]

    access_resp = await authenticated_client.get(f"/api/v1/projects/{project_id}/access")
    creator_entry = next((a for a in access_resp.json() if a["user_id"] == seed_user["user_id"]), None)
    assert creator_entry is not None
    assert creator_entry["permission"] == "admin"


# ---------------------------------------------------------------------------
# 6. GET project — field and permission checks
# ---------------------------------------------------------------------------


async def test_get_project_returns_source_and_target_vendor(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    create_resp = await authenticated_client.post(
        "/api/v1/projects",
        json=_draft_payload(
            seed_user["org_id"],
            source_vendor_id="sap",
            source_product_id="sap",
            target_vendor_id="microsoft",
            target_product_id="microsoft_dynamics",
        ),
    )
    project_id = create_resp.json()["id"]

    resp = await authenticated_client.get(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_vendor_id"] == "sap"
    assert data["target_vendor_id"] == "microsoft"


async def test_get_project_not_found_returns_404(authenticated_client: AsyncClient):
    resp = await authenticated_client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_get_project_without_access_returns_403(
    authenticated_client: AsyncClient,
    test_client: AsyncClient,
    seed_user: dict[str, Any],
):
    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]

    stranger_id = await _register_and_verify(test_client, "stranger@example.com", "Stranger Org")
    stranger_token = await _get_token_for(stranger_id)

    resp = await test_client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. List projects
# ---------------------------------------------------------------------------


async def test_list_projects_returns_paginated_response(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    resp = await authenticated_client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert "total" in data
    assert len(data["projects"]) >= 1


async def test_list_projects_filtered_by_org_id(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    resp = await authenticated_client.get(f"/api/v1/projects?org_id={seed_user['org_id']}")
    assert resp.status_code == 200
    assert all(p["org_id"] == seed_user["org_id"] for p in resp.json()["projects"])


# ---------------------------------------------------------------------------
# 8. PATCH project
# ---------------------------------------------------------------------------


async def test_patch_project_updates_erp_vendor_fields(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]

    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"source_vendor_id": "oracle", "target_vendor_id": "microsoft"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_vendor_id"] == "oracle"
    assert data["target_vendor_id"] == "microsoft"


async def test_patch_project_updates_name_and_description(authenticated_client: AsyncClient, seed_user: dict[str, Any]):
    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]

    resp = await authenticated_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Name", "description": "Updated description"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated description"


async def test_patch_project_viewer_access_returns_403(
    authenticated_client: AsyncClient,
    test_client: AsyncClient,
    seed_user: dict[str, Any],
):
    viewer_email = "viewer_patch@example.com"
    viewer_id = await _register_and_verify(test_client, viewer_email, "Viewer Org")
    await _add_to_org(viewer_id, seed_user["org_id"])
    viewer_token = await _get_token_for(viewer_id)

    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]

    await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": viewer_email, "permission": "viewer"},
    )

    resp = await test_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Unauthorized Update"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. DELETE project
# ---------------------------------------------------------------------------


async def test_delete_project_by_admin_returns_deleted_status(
    authenticated_client: AsyncClient, seed_user: dict[str, Any]
):
    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]
    resp = await authenticated_client.delete(f"/api/v1/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_delete_project_editor_returns_403(
    authenticated_client: AsyncClient, test_client: AsyncClient, seed_user: dict[str, Any]
):
    editor_email = "editor_del@example.com"
    editor_id = await _register_and_verify(test_client, editor_email, "Editor Del Org")
    await _add_to_org(editor_id, seed_user["org_id"])
    editor_token = await _get_token_for(editor_id)

    create_resp = await authenticated_client.post("/api/v1/projects", json=_draft_payload(seed_user["org_id"]))
    project_id = create_resp.json()["id"]

    await authenticated_client.post(
        f"/api/v1/projects/{project_id}/access",
        json={"email": editor_email, "permission": "editor"},
    )

    resp = await test_client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {editor_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 10. Unauthenticated requests — must return 401
# ---------------------------------------------------------------------------


async def test_create_project_unauthenticated_returns_401(test_client: AsyncClient, seed_user: dict[str, Any]):
    """POST without a token returns 401 (Authorization header is required)."""
    resp = await test_client.post(
        "/api/v1/projects",
        json={"name": "No Auth", "org_id": seed_user["org_id"]},
    )
    assert resp.status_code == 401


async def test_list_projects_unauthenticated_returns_401(test_client: AsyncClient):
    """GET without a token returns 401 (Authorization header is required)."""
    resp = await test_client.get("/api/v1/projects")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 11. ERP catalogue endpoints (wizard Step 1 UI data)
# ---------------------------------------------------------------------------


async def test_get_vendors_returns_all_yaml_vendors(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/vendors")
    assert resp.status_code == 200
    vendor_ids = {v["id"] for v in resp.json()}
    for expected in ("sap", "microsoft", "oracle", "sage", "xero", "odoo", "intuit", "zoho"):
        assert expected in vendor_ids


async def test_get_products_for_sap_vendor(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/vendors/sap/products")
    assert resp.status_code == 200
    assert any(p["id"] == "sap" for p in resp.json())


async def test_get_products_for_microsoft_vendor(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/vendors/microsoft/products")
    assert resp.status_code == 200
    assert any(p["id"] == "microsoft_dynamics" for p in resp.json())


async def test_get_products_for_unknown_vendor_returns_404(test_client: AsyncClient):
    """An unknown vendor ID returns 404 on the vendor-products cascade endpoint."""
    resp = await test_client.get("/api/v1/erp-systems/vendors/unknown_xyz/products")
    assert resp.status_code == 404


async def test_get_connection_methods_for_sap(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/sap/connection-methods")
    assert resp.status_code == 200
    method_ids = {m["id"] for m in resp.json()}
    assert "csv_file" in method_ids
    assert "on_premise" in method_ids
    assert "cloud_saas" not in method_ids


async def test_get_connection_methods_for_oracle_netsuite(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/oracle_netsuite/connection-methods")
    assert resp.status_code == 200
    method_ids = {m["id"] for m in resp.json()}
    assert "cloud_saas" in method_ids
    assert "csv_file" in method_ids


async def test_get_connection_methods_unknown_product_returns_empty(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems/nonexistent_erp/connection-methods")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_all_erp_systems_returns_full_catalogue(test_client: AsyncClient):
    resp = await test_client.get("/api/v1/erp-systems")
    assert resp.status_code == 200
    system_ids = {s["id"] for s in resp.json()}
    for expected in (
        "sap",
        "oracle_netsuite",
        "microsoft_dynamics",
        "quickbooks",
        "sage",
        "xero",
        "pastel",
        "odoo",
        "zoho",
    ):
        assert expected in system_ids
