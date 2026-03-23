"""
COA Migration - Authentication and Dashboard API Tests
Tests the new login, dashboard, and project access flow endpoints.

Endpoints tested:
- POST /api/auth/login - Login with user_id returns user data and token
- GET /api/auth/me - Get current user from token
- POST /api/auth/logout - Logout endpoint
- GET /api/dashboard/companies - Returns companies and projects for authenticated user
- GET /api/dashboard/projects/{id} - Returns project details with saved mappings
- POST /api/dashboard/projects - Creates a new project
- POST /api/dashboard/projects/{id}/access - Grants user access to project
- PATCH /api/dashboard/projects/{id} - Update project
- POST /api/dashboard/projects/{id}/mappings - Save mappings to project
- DELETE /api/dashboard/projects/{id}/access/{user_id} - Revoke user access
"""
import pytest
import requests
import os
import uuid

# Get BASE URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://migrate-persist-db.preview.emergentagent.com"


class TestAuthLogin:
    """Test authentication login endpoint"""

    def test_login_existing_user_admin(self):
        """POST /api/auth/login with admin user returns user data and token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "admin"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True, "Expected success=True"
        assert "user" in data, "Response should contain 'user'"
        assert "token" in data, "Response should contain 'token'"
        
        # Validate user data
        user = data["user"]
        assert user["user_id"] == "admin", f"Expected user_id 'admin', got {user['user_id']}"
        assert user["name"] == "Admin User", f"Expected name 'Admin User', got {user['name']}"
        assert user["email"] == "admin@company.com", f"Expected email 'admin@company.com', got {user['email']}"
        
        # Validate token format
        assert data["token"] == "mock-token-admin", f"Expected token 'mock-token-admin', got {data['token']}"
        
        print(f"PASS: Login admin user returns token and user data")

    def test_login_existing_user_john_doe(self):
        """POST /api/auth/login with john.doe user returns user data and token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "john.doe"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data["user"]["user_id"] == "john.doe"
        assert data["user"]["name"] == "John Doe"
        assert data["token"] == "mock-token-john.doe"
        
        print(f"PASS: Login john.doe user returns correct data")

    def test_login_existing_user_jane_smith(self):
        """POST /api/auth/login with jane.smith user returns user data and token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "jane.smith"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data["user"]["user_id"] == "jane.smith"
        assert data["user"]["name"] == "Jane Smith"
        assert data["token"] == "mock-token-jane.smith"
        
        print(f"PASS: Login jane.smith user returns correct data")

    def test_login_new_user_auto_creates(self):
        """POST /api/auth/login with new user_id auto-creates user"""
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": test_user_id},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("is_new_user") == True, "New user should have is_new_user=True"
        assert data["user"]["user_id"] == test_user_id.lower()  # user_id is lowercased
        assert f"mock-token-{test_user_id.lower()}" == data["token"]
        
        print(f"PASS: Login with new user '{test_user_id}' auto-creates user")

    def test_login_user_id_case_insensitive(self):
        """POST /api/auth/login normalizes user_id to lowercase"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "ADMIN"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Should match existing admin user
        assert data["user"]["user_id"] == "admin"
        
        print(f"PASS: Login user_id is case-insensitive")


class TestAuthMe:
    """Test GET /api/auth/me endpoint"""

    def test_get_current_user_with_valid_token(self):
        """GET /api/auth/me with valid token returns user data"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        user = response.json()
        assert user["user_id"] == "admin"
        assert user["name"] == "Admin User"
        
        print(f"PASS: GET /api/auth/me returns admin user with valid token")

    def test_get_current_user_without_token(self):
        """GET /api/auth/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"PASS: GET /api/auth/me returns 401 without token")

    def test_get_current_user_with_invalid_token(self):
        """GET /api/auth/me with invalid token returns 401"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"PASS: GET /api/auth/me returns 401 with invalid token")


class TestAuthLogout:
    """Test POST /api/auth/logout endpoint"""

    def test_logout_returns_success(self):
        """POST /api/auth/logout returns success"""
        response = requests.post(f"{BASE_URL}/api/auth/logout")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        
        print(f"PASS: POST /api/auth/logout returns success")


class TestDashboardCompanies:
    """Test GET /api/dashboard/companies endpoint"""

    def test_get_companies_for_admin_user(self):
        """GET /api/dashboard/companies for admin returns all companies"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "companies" in data, "Response should contain 'companies'"
        assert "total_projects" in data, "Response should contain 'total_projects'"
        
        companies = data["companies"]
        assert isinstance(companies, list), "companies should be a list"
        
        # Admin should have access to all 3 projects (p-001, p-002, p-003)
        assert data["total_projects"] >= 2, f"Admin should have access to at least 2 projects, got {data['total_projects']}"
        
        # Verify company structure
        if len(companies) > 0:
            company = companies[0]
            assert "id" in company, "Company should have 'id'"
            assert "name" in company, "Company should have 'name'"
            assert "projects" in company, "Company should have 'projects'"
            
            # Verify project structure within company
            if len(company["projects"]) > 0:
                project = company["projects"][0]
                assert "id" in project, "Project should have 'id'"
                assert "name" in project, "Project should have 'name'"
                assert "status" in project, "Project should have 'status'"
                assert "user_permission" in project, "Project should have 'user_permission'"
                assert "mapping_count" in project, "Project should have 'mapping_count'"
                assert "access_list" in project, "Project should have 'access_list'"
        
        print(f"PASS: GET /api/dashboard/companies returns {len(companies)} companies with {data['total_projects']} projects for admin")

    def test_get_companies_for_john_doe(self):
        """GET /api/dashboard/companies for john.doe returns ACME projects"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # john.doe should have access to p-001 and p-002 (both in acme-corp)
        assert data["total_projects"] >= 1, f"john.doe should have access to projects"
        
        # Verify john.doe sees ACME Corporation
        company_names = [c["name"] for c in data["companies"]]
        assert "ACME Corporation" in company_names, "john.doe should see ACME Corporation"
        
        print(f"PASS: john.doe sees {data['total_projects']} projects including ACME Corporation")

    def test_get_companies_without_auth(self):
        """GET /api/dashboard/companies without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/dashboard/companies")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"PASS: GET /api/dashboard/companies returns 401 without auth")

    def test_companies_show_project_status_and_mapping_count(self):
        """Dashboard shows project status and mapping count"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        
        data = response.json()
        found_status = False
        found_mapping = False
        
        for company in data["companies"]:
            for project in company["projects"]:
                # Check status field exists and has valid value
                if "status" in project:
                    found_status = True
                    valid_statuses = ["draft", "in_progress", "pending_review", "completed"]
                    assert project["status"] in valid_statuses, f"Invalid status: {project['status']}"
                
                # Check mapping_count exists
                if "mapping_count" in project:
                    found_mapping = True
                    assert isinstance(project["mapping_count"], int), "mapping_count should be int"
        
        assert found_status, "At least one project should have status"
        assert found_mapping, "At least one project should have mapping_count"
        
        print(f"PASS: Dashboard shows project status and mapping count")


class TestDashboardProjectDetail:
    """Test GET /api/dashboard/projects/{id} endpoint"""

    def test_get_project_detail_p001(self):
        """GET /api/dashboard/projects/p-001 returns project details with mappings"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        project = response.json()
        
        # Verify project data
        assert project["id"] == "p-001", f"Expected id 'p-001', got {project['id']}"
        assert project["name"] == "QuickBooks to Xero Migration"
        assert project["source_erp"] == "quickbooks"
        assert project["target_erp"] == "xero"
        assert project["status"] == "in_progress"
        
        # Verify mappings are included
        assert "mappings" in project, "Project should include mappings"
        assert isinstance(project["mappings"], list), "mappings should be a list"
        assert project["mapping_count"] >= 1, "p-001 should have saved mappings"
        
        # Verify mapping_stats
        assert "mapping_stats" in project, "Project should have mapping_stats"
        assert "total" in project["mapping_stats"]
        assert "approved" in project["mapping_stats"]
        assert "suggested" in project["mapping_stats"]
        
        # Verify access_list
        assert "access_list" in project, "Project should have access_list"
        assert len(project["access_list"]) >= 1, "p-001 should have users with access"
        
        print(f"PASS: GET /api/dashboard/projects/p-001 returns project with {project['mapping_count']} mappings")

    def test_get_project_detail_completed_status(self):
        """GET /api/dashboard/projects/p-002 returns completed project"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-002",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        
        project = response.json()
        assert project["id"] == "p-002"
        assert project["status"] == "completed"
        
        print(f"PASS: GET /api/dashboard/projects/p-002 returns completed project")

    def test_get_project_detail_nonexistent(self):
        """GET /api/dashboard/projects/nonexistent returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/nonexistent",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        print(f"PASS: GET /api/dashboard/projects/nonexistent returns 404")

    def test_get_project_detail_no_access(self):
        """GET /api/dashboard/projects/{id} returns 403 for user without access"""
        # Create a new user who doesn't have access to p-001
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "TEST_newuser_no_access"},
            headers={"Content-Type": "application/json"}
        )
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-test_newuser_no_access"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"PASS: GET /api/dashboard/projects/p-001 returns 403 for user without access")

    def test_get_project_without_auth(self):
        """GET /api/dashboard/projects/{id} without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/dashboard/projects/p-001")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"PASS: GET /api/dashboard/projects/p-001 returns 401 without auth")


class TestCreateProject:
    """Test POST /api/dashboard/projects endpoint"""

    def test_create_new_project_success(self):
        """POST /api/dashboard/projects creates a new project"""
        project_name = f"TEST_New_Migration_{uuid.uuid4().hex[:6]}"
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            json={
                "name": project_name,
                "company_id": "acme-corp",
                "source_erp": "quickbooks",
                "target_erp": "xero",
                "description": "Test project creation"
            },
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert "project" in data
        
        project = data["project"]
        assert project["name"] == project_name
        assert project["company_id"] == "acme-corp"
        assert project["source_erp"] == "quickbooks"
        assert project["target_erp"] == "xero"
        assert project["status"] == "draft"  # New projects start as draft
        assert "id" in project  # Should have generated ID
        
        print(f"PASS: Created new project '{project_name}' with id {project['id']}")
        return project["id"]

    def test_create_project_auto_creates_company(self):
        """POST /api/dashboard/projects auto-creates company if not exists"""
        new_company_id = f"test-company-{uuid.uuid4().hex[:6]}"
        project_name = f"TEST_Auto_Company_{uuid.uuid4().hex[:6]}"
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            json={
                "name": project_name,
                "company_id": new_company_id,
                "source_erp": "sap",
                "target_erp": "oracle_netsuite"
            },
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data["project"]["company_id"] == new_company_id
        
        print(f"PASS: Created project with auto-created company '{new_company_id}'")

    def test_create_project_without_auth(self):
        """POST /api/dashboard/projects without auth returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            json={
                "name": "Test",
                "company_id": "test",
                "source_erp": "sap",
                "target_erp": "xero"
            },
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"PASS: POST /api/dashboard/projects returns 401 without auth")


class TestProjectAccess:
    """Test POST /api/dashboard/projects/{id}/access endpoint"""

    def test_grant_project_access(self):
        """POST /api/dashboard/projects/{id}/access grants user access"""
        # First create a new test user
        test_user = f"test_access_user_{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": test_user}
        )
        
        # Admin grants access to this user on p-001
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            json={
                "user_id": test_user,
                "permission": "viewer"
            },
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        
        # Verify user can now access the project
        verify_response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": f"Bearer mock-token-{test_user.lower()}"}
        )
        assert verify_response.status_code == 200, "Granted user should be able to access project"
        
        print(f"PASS: Granted '{test_user}' viewer access to p-001")

    def test_grant_access_different_permissions(self):
        """POST /api/dashboard/projects/{id}/access with different permission levels"""
        permissions = ["viewer", "editor", "approver", "admin"]
        
        for perm in permissions:
            test_user = f"test_{perm}_{uuid.uuid4().hex[:4]}"
            response = requests.post(
                f"{BASE_URL}/api/dashboard/projects/p-001/access",
                json={
                    "user_id": test_user,
                    "permission": perm
                },
                headers={
                    "Authorization": "Bearer mock-token-admin",
                    "Content-Type": "application/json"
                }
            )
            assert response.status_code == 200, f"Failed to grant {perm} permission"
        
        print(f"PASS: Granted all permission levels successfully")

    def test_grant_access_non_admin_fails(self):
        """POST /api/dashboard/projects/{id}/access by viewer fails"""
        # jane.smith has viewer permission on p-001
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            json={
                "user_id": "some_user",
                "permission": "viewer"
            },
            headers={
                "Authorization": "Bearer mock-token-jane.smith",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"PASS: Viewer cannot grant access (returns 403)")

    def test_grant_access_to_nonexistent_project(self):
        """POST /api/dashboard/projects/nonexistent/access returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/nonexistent/access",
            json={"user_id": "test", "permission": "viewer"},
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        print(f"PASS: Grant access to nonexistent project returns 404")


class TestUpdateProject:
    """Test PATCH /api/dashboard/projects/{id} endpoint"""

    def test_update_project_status(self):
        """PATCH /api/dashboard/projects/{id} updates status"""
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            json={"status": "pending_review"},
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        
        # Reset status
        requests.patch(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            json={"status": "in_progress"},
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        
        print(f"PASS: PATCH /api/dashboard/projects/p-001 updates status")

    def test_update_project_viewer_fails(self):
        """PATCH /api/dashboard/projects/{id} by viewer returns 403"""
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            json={"status": "completed"},
            headers={
                "Authorization": "Bearer mock-token-jane.smith",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"PASS: Viewer cannot update project (returns 403)")


class TestSaveMappings:
    """Test POST /api/dashboard/projects/{id}/mappings endpoint"""

    def test_save_mappings_to_project(self):
        """POST /api/dashboard/projects/{id}/mappings saves mappings"""
        mappings = [
            {
                "id": "test-m-001",
                "source_account_name": "Test Checking",
                "source_account_type": "Bank",
                "target_account_name": "Bank Account",
                "target_account_type": "BANK",
                "confidence_score": 95.0,
                "status": "approved",
                "remark": "user"
            },
            {
                "id": "test-m-002",
                "source_account_name": "Test Sales",
                "source_account_type": "Income",
                "target_account_name": "Revenue",
                "target_account_type": "REVENUE",
                "confidence_score": 88.0,
                "status": "suggested",
                "remark": "ai"
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/mappings",
            json=mappings,
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("mapping_count") == 2
        
        # Verify mappings were saved by fetching project
        verify = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        project = verify.json()
        assert project["mapping_count"] == 2
        
        print(f"PASS: Saved {data['mapping_count']} mappings to p-001")

    def test_save_mappings_viewer_fails(self):
        """POST /api/dashboard/projects/{id}/mappings by viewer returns 403"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/mappings",
            json=[{"id": "test", "source_account_name": "Test"}],
            headers={
                "Authorization": "Bearer mock-token-jane.smith",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"PASS: Viewer cannot save mappings (returns 403)")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
