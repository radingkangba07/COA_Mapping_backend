"""End-to-end integration test covering full COA migration workflow.

Steps:
1) Login (auto-create user) → 2) Create company → 3) Create project (auto-admin)
4) List ERP systems → 5) Fuzzy match columns → 6) Hierarchical mapping
7) Bulk save mappings (project status → in_progress) → 8) Get stats
9) Export as Excel → 10) List project files
11) Create job (sync fallback) → 12) Dashboard → 13) Grant access
14) Viewer can read but not edit → 15) Revoke access
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.core.database import get_db
from src.main import app


@pytest.mark.asyncio
async def test_full_workflow(db_session):
    """Single test covering the full user journey."""

    # Override deps
    app.dependency_overrides[get_db] = lambda: db_session

    from src.tests.conftest import get_test_settings

    app.dependency_overrides[get_settings] = get_test_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1) Login (auto-creates user)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"user_id": "workflow"},
        )
        assert resp.status_code == 200
        tokens = resp.json()
        auth = {"Authorization": f"Bearer {tokens['token']}"}

        # 2) Create company
        resp = await client.post(
            "/api/v1/companies",
            json={"slug": "workflow-co", "name": "Workflow Company"},
            headers=auth,
        )
        assert resp.status_code == 201

        # 3) Create project (auto-admin)
        resp = await client.post(
            "/api/v1/projects",
            json={
                "name": "Workflow Project",
                "company_id": "workflow-proj-co",
                "company_name": "Workflow Proj Co",
                "source_system": "quickbooks",
                "target_system": "xero",
            },
            headers=auth,
        )
        assert resp.status_code == 201
        project = resp.json()
        project_id = project["id"]
        assert project["status"] == "draft"

        # Verify auto-admin
        resp = await client.get(f"/api/v1/projects/{project_id}/access", headers=auth)
        assert resp.status_code == 200
        assert any(a["permission"] == "admin" for a in resp.json())

        # 4) List ERP systems
        resp = await client.get("/api/v1/erp-systems")
        assert resp.status_code == 200
        erp_systems = resp.json()
        assert len(erp_systems) == 9

        # 5) Fuzzy match columns
        resp = await client.post(
            "/api/v1/mappings/fuzzy-match",
            json={
                "source_columns": ["Account Name", "Account Type", "Account Number"],
                "target_system": "xero",
                "threshold": 60,
            },
            headers=auth,
        )
        assert resp.status_code == 200
        fuzzy = resp.json()
        assert len(fuzzy["mappings"]) == 3

        # 6) Hierarchical mapping — creates a job (sync fallback, no NATS in tests)
        resp = await client.post(
            "/api/v1/mappings/hierarchical",
            json={
                "project_id": project_id,
                "source_file_id": "00000000-0000-0000-0000-000000000001",
                "target_file_id": "00000000-0000-0000-0000-000000000002",
            },
            headers=auth,
        )
        assert resp.status_code == 201
        hier = resp.json()
        assert hier["project_id"] == project_id
        assert hier["status"] == "completed"  # sync fallback
        assert "job_id" in hier

        # 7) Bulk save mappings
        resp = await client.post(
            f"/api/v1/mappings/project/{project_id}",
            json=[
                {
                    "source_account_name": "Sales Revenue",
                    "source_account_number": "4000",
                    "source_account_type": "Income",
                    "target_account_name": "Sales",
                    "target_account_number": "200",
                    "target_account_type": "Revenue",
                    "confidence_score": 92.5,
                    "status": "suggested",
                },
                {
                    "source_account_name": "Office Rent",
                    "source_account_number": "5000",
                    "source_account_type": "Expense",
                    "target_account_name": "Rent",
                    "target_account_number": "400",
                    "target_account_type": "Overheads",
                    "confidence_score": 85.0,
                    "status": "suggested",
                },
            ],
            headers=auth,
        )
        assert resp.status_code == 201
        assert resp.json()["mapping_count"] == 2

        # Verify project status auto-transitioned to in_progress
        resp = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
        assert resp.json()["status"] == "in_progress"

        # 8) Get mapping stats
        resp = await client.get(f"/api/v1/mappings/project/{project_id}/stats", headers=auth)
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] == 2
        assert stats["suggested"] == 2

        # 9) Export as Excel
        resp = await client.post(f"/api/v1/mappings/project/{project_id}/export", headers=auth)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

        # 10) List project files
        resp = await client.get(f"/api/v1/storage/project/{project_id}/files", headers=auth)
        assert resp.status_code == 200

        # 11) Create job (sync fallback)
        resp = await client.post(
            "/api/v1/jobs",
            json={"project_id": project_id, "job_type": "account_matching"},
            headers=auth,
        )
        assert resp.status_code == 201
        job = resp.json()
        assert job["status"] == "completed"

        # 12) Dashboard
        resp = await client.get("/api/v1/dashboard/companies", headers=auth)
        assert resp.status_code == 200
        dashboard = resp.json()
        assert "companies" in dashboard
        assert len(dashboard["companies"]) >= 1
        # Find our project's company
        found = False
        for company in dashboard["companies"]:
            for p in company["projects"]:
                if p["id"] == project_id:
                    assert p["mapping_count"] == 2
                    found = True
        assert found, "Project not found in dashboard"

        # 13) Login as second user and grant viewer access
        resp = await client.post(
            "/api/v1/auth/login",
            json={"user_id": "viewer"},
        )
        assert resp.status_code == 200
        viewer_uuid = resp.json()["user"]["id"]

        resp = await client.post(
            f"/api/v1/projects/{project_id}/access",
            json={"user_id": viewer_uuid, "permission": "viewer"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Login as viewer
        viewer_auth = {"Authorization": "Bearer mock-token-viewer"}

        # 14) Viewer can read
        resp = await client.get(f"/api/v1/projects/{project_id}", headers=viewer_auth)
        assert resp.status_code == 200

        # Viewer can't edit (editor+ required for PATCH)
        resp = await client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "Hacked Name"},
            headers=viewer_auth,
        )
        assert resp.status_code == 403

        # 15) Revoke access
        resp = await client.delete(
            f"/api/v1/projects/{project_id}/access/{viewer_uuid}",
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    app.dependency_overrides.clear()
