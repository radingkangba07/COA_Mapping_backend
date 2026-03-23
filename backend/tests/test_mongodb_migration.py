"""
Comprehensive test suite for COA Migration MongoDB persistence.
Tests: Auth, Dashboard, Project CRUD, Mappings, Access Control
"""
import pytest
import requests
import os
import uuid

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")


class TestHealthCheck:
    """Health endpoint tests - MongoDB connection status"""
    
    def test_health_returns_database_status(self):
        """GET /api/health - Returns database connection status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "database" in data
        assert data["database"] == "connected"
        assert data["architecture"] == "mongodb-persistent"
        print(f"Health check passed: database={data['database']}, storage={data.get('storage')}")


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_existing_user_admin(self):
        """POST /api/auth/login - Login with existing admin user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["is_new_user"] is False
        assert data["user"]["user_id"] == "admin"
        assert data["token"] == "mock-token-admin"
        assert "email" in data["user"]
        print(f"Login admin: user_id={data['user']['user_id']}, name={data['user']['name']}")
    
    def test_login_existing_user_john_doe(self):
        """POST /api/auth/login - Login with john.doe user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "john.doe"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["user"]["user_id"] == "john.doe"
        assert data["user"]["name"] == "John Doe"
        print(f"Login john.doe: email={data['user'].get('email')}")
    
    def test_login_existing_user_jane_smith(self):
        """POST /api/auth/login - Login with jane.smith user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "jane.smith"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["user"]["user_id"] == "jane.smith"
        print(f"Login jane.smith: name={data['user']['name']}")
    
    def test_login_new_user_auto_create(self):
        """POST /api/auth/login - New user auto-creates on first login"""
        test_user_id = f"test.user.{uuid.uuid4().hex[:6]}"
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": test_user_id}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["is_new_user"] is True
        assert data["user"]["user_id"] == test_user_id.lower()
        print(f"New user auto-created: {test_user_id}")
    
    def test_login_case_insensitive(self):
        """POST /api/auth/login - User ID is case-insensitive"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "ADMIN"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["user"]["user_id"] == "admin"
        print("Case-insensitive login verified")
    
    def test_get_current_user_valid_token(self):
        """GET /api/auth/me - Returns user with valid token"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["user_id"] == "admin"
        assert "name" in data
        assert "email" in data
        print(f"Current user: {data['user_id']}, last_login={data.get('last_login')}")
    
    def test_get_current_user_no_token(self):
        """GET /api/auth/me - Returns 401 without token"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 401
        print("401 returned for missing token")
    
    def test_get_current_user_invalid_token(self):
        """GET /api/auth/me - Returns 401 with invalid token"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid-token-xyz"}
        )
        assert response.status_code == 401
        print("401 returned for invalid token")
    
    def test_logout(self):
        """POST /api/auth/logout - Returns success"""
        response = requests.post(f"{BASE_URL}/api/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("Logout successful")


class TestDashboardCompanies:
    """Dashboard companies endpoint tests"""
    
    def test_get_companies_admin(self):
        """GET /api/dashboard/companies - Returns companies and projects for admin"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "companies" in data
        assert "total_projects" in data
        assert data["total_projects"] >= 3  # Seed data has 3+ projects
        
        # Verify company structure
        companies = data["companies"]
        assert len(companies) >= 2  # At least ACME and Globex
        
        # Check ACME exists with projects
        acme = next((c for c in companies if c["company_id"] == "acme-corp"), None)
        assert acme is not None
        assert acme["name"] == "ACME Corporation"
        assert len(acme["projects"]) >= 2
        print(f"Admin sees {len(companies)} companies with {data['total_projects']} total projects")
    
    def test_get_companies_john_doe(self):
        """GET /api/dashboard/companies - Returns correct data for john.doe"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_projects"] >= 2
        
        # John has access to ACME projects only (based on seed data)
        company_ids = [c["company_id"] for c in data["companies"]]
        assert "acme-corp" in company_ids
        print(f"john.doe sees companies: {company_ids}")
    
    def test_get_companies_no_auth(self):
        """GET /api/dashboard/companies - Returns 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/dashboard/companies")
        assert response.status_code == 401
        print("401 returned for missing auth")
    
    def test_company_project_has_access_list(self):
        """GET /api/dashboard/companies - Projects include access list"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Get first project
        project = data["companies"][0]["projects"][0]
        
        assert "access_list" in project
        assert "user_permission" in project
        assert "mapping_count" in project
        assert "status" in project
        print(f"Project has access_list with {len(project['access_list'])} users")


class TestProjectDetails:
    """Project detail endpoint tests"""
    
    def test_get_project_detail_p001(self):
        """GET /api/dashboard/projects/p-001 - Returns project with saved mappings"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "p-001"
        assert data["name"] == "QuickBooks to Xero Migration"
        assert data["source_erp"] == "quickbooks"
        assert data["target_erp"] == "xero"
        assert "mappings" in data
        assert "mapping_count" in data
        assert "access_list" in data
        assert "company" in data
        assert data["company"]["name"] == "ACME Corporation"
        print(f"Project p-001: {data['mapping_count']} mappings, status={data['status']}")
    
    def test_get_project_detail_completed(self):
        """GET /api/dashboard/projects/p-002 - Returns completed project"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-002",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == "p-002"
        assert data["status"] == "completed"
        print(f"Project p-002: status={data['status']}")
    
    def test_get_project_detail_not_found(self):
        """GET /api/dashboard/projects/nonexistent - Returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/nonexistent-project",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 404
        print("404 returned for nonexistent project")
    
    def test_get_project_detail_no_access(self):
        """GET /api/dashboard/projects/{id} - Returns 403 for user without access"""
        # Create a new user who has no access to p-001
        test_user = f"test.noaccess.{uuid.uuid4().hex[:6]}"
        requests.post(f"{BASE_URL}/api/auth/login", json={"user_id": test_user})
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": f"Bearer mock-token-{test_user}"}
        )
        assert response.status_code == 403
        print("403 returned for user without access")
    
    def test_get_project_detail_no_auth(self):
        """GET /api/dashboard/projects/{id} - Returns 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/dashboard/projects/p-001")
        assert response.status_code == 401
        print("401 returned for missing auth")


class TestProjectCreate:
    """Project creation endpoint tests"""
    
    def test_create_project_success(self):
        """POST /api/dashboard/projects - Creates new project"""
        project_name = f"TEST_Project_{uuid.uuid4().hex[:6]}"
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={
                "name": project_name,
                "source_erp": "quickbooks",
                "target_erp": "xero",
                "company_id": "acme-corp",
                "description": "Test project"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["project"]["name"] == project_name
        assert data["project"]["status"] == "draft"
        assert data["project"]["created_by"] == "admin"
        print(f"Created project: {data['project']['id']}, name={project_name}")
        
        # Verify project appears in dashboard
        dash_response = requests.get(
            f"{BASE_URL}/api/dashboard/companies",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        all_projects = []
        for company in dash_response.json()["companies"]:
            all_projects.extend(company["projects"])
        project_names = [p["name"] for p in all_projects]
        assert project_name in project_names
        print("Project verified in dashboard")
    
    def test_create_project_auto_creates_company(self):
        """POST /api/dashboard/projects - Auto-creates company if not exists"""
        new_company_id = f"test-company-{uuid.uuid4().hex[:6]}"
        project_name = f"TEST_AutoCompany_{uuid.uuid4().hex[:6]}"
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={
                "name": project_name,
                "source_erp": "sap",
                "target_erp": "oracle_netsuite",
                "company_id": new_company_id,
                "description": "Test auto-company"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["project"]["company_id"] == new_company_id
        print(f"Auto-created company: {new_company_id}")
    
    def test_create_project_no_auth(self):
        """POST /api/dashboard/projects - Returns 401 without auth"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            json={
                "name": "Test",
                "source_erp": "quickbooks",
                "target_erp": "xero",
                "company_id": "test"
            }
        )
        assert response.status_code == 401
        print("401 returned for missing auth")


class TestProjectUpdate:
    """Project update endpoint tests"""
    
    @pytest.fixture
    def created_project(self):
        """Create a test project for update tests"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={
                "name": f"TEST_Update_{uuid.uuid4().hex[:6]}",
                "source_erp": "quickbooks",
                "target_erp": "xero",
                "company_id": "acme-corp"
            }
        )
        return response.json()["project"]
    
    def test_update_project_status(self, created_project):
        """PATCH /api/dashboard/projects/{id} - Updates project status"""
        project_id = created_project["id"]
        
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/projects/{project_id}",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"status": "in_progress"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["project"]["status"] == "in_progress"
        print(f"Updated project {project_id} status to in_progress")
    
    def test_update_project_name(self, created_project):
        """PATCH /api/dashboard/projects/{id} - Updates project name"""
        project_id = created_project["id"]
        new_name = f"Updated_Name_{uuid.uuid4().hex[:4]}"
        
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/projects/{project_id}",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"name": new_name}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["project"]["name"] == new_name
        print(f"Updated project name to {new_name}")
    
    def test_update_project_viewer_denied(self):
        """PATCH /api/dashboard/projects/{id} - Viewer cannot update (403)"""
        # jane.smith is viewer on p-001
        response = requests.patch(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-jane.smith"},
            json={"status": "completed"}
        )
        assert response.status_code == 403
        print("403 returned for viewer trying to update")


class TestProjectMappings:
    """Project mappings endpoint tests"""
    
    def test_save_mappings_success(self):
        """POST /api/dashboard/projects/{id}/mappings - Saves mappings"""
        mappings = [
            {
                "source_account_name": f"TEST_Account_{uuid.uuid4().hex[:4]}",
                "source_account_type": "Bank",
                "target_account_name": "Business Bank",
                "target_account_type": "BANK",
                "confidence_score": 95.0,
                "status": "approved"
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/mappings",
            headers={"Authorization": "Bearer mock-token-john.doe"},
            json=mappings
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["mapping_count"] == 1
        assert "saved_by" in data
        print(f"Saved {data['mapping_count']} mappings by {data['saved_by']}")
        
        # Verify mappings persisted via GET
        detail_response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        project = detail_response.json()
        assert project["mapping_count"] >= 1
        print(f"Verified {project['mapping_count']} mappings in project")
    
    def test_save_mappings_viewer_denied(self):
        """POST /api/dashboard/projects/{id}/mappings - Viewer cannot save (403)"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/mappings",
            headers={"Authorization": "Bearer mock-token-jane.smith"},
            json=[{"source_account_name": "Test", "target_account_name": "Test"}]
        )
        assert response.status_code == 403
        print("403 returned for viewer trying to save mappings")


class TestProjectAccess:
    """Project access management endpoint tests"""
    
    def test_grant_access_success(self):
        """POST /api/dashboard/projects/{id}/access - Grants access"""
        test_user = f"test.grantee.{uuid.uuid4().hex[:6]}"
        
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"user_id": test_user, "permission": "editor"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert test_user in data["message"]
        print(f"Granted editor access to {test_user}")
        
        # Verify access via project detail
        detail_response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        access_users = [a["user_id"] for a in detail_response.json()["access_list"]]
        assert test_user in access_users
        print(f"Verified {test_user} in access list")
    
    def test_grant_access_all_permissions(self):
        """POST /api/dashboard/projects/{id}/access - Supports all permission levels"""
        for perm in ["viewer", "editor", "approver", "admin"]:
            test_user = f"test.perm.{uuid.uuid4().hex[:6]}"
            response = requests.post(
                f"{BASE_URL}/api/dashboard/projects/p-001/access",
                headers={"Authorization": "Bearer mock-token-admin"},
                json={"user_id": test_user, "permission": perm}
            )
            assert response.status_code == 200
            print(f"Granted {perm} permission successfully")
    
    def test_grant_access_viewer_denied(self):
        """POST /api/dashboard/projects/{id}/access - Viewer cannot grant access (403)"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            headers={"Authorization": "Bearer mock-token-jane.smith"},
            json={"user_id": "test.user", "permission": "viewer"}
        )
        assert response.status_code == 403
        print("403 returned for viewer trying to grant access")
    
    def test_grant_access_project_not_found(self):
        """POST /api/dashboard/projects/{id}/access - Returns 404 for nonexistent project"""
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects/nonexistent/access",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"user_id": "test.user", "permission": "viewer"}
        )
        assert response.status_code == 404
        print("404 returned for nonexistent project")
    
    def test_revoke_access_success(self):
        """DELETE /api/dashboard/projects/{id}/access/{user_id} - Revokes access"""
        # First grant access
        test_user = f"test.revoke.{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"user_id": test_user, "permission": "viewer"}
        )
        
        # Then revoke
        response = requests.delete(
            f"{BASE_URL}/api/dashboard/projects/p-001/access/{test_user}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        print(f"Revoked access from {test_user}")
        
        # Verify user no longer has access
        detail_response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        access_users = [a["user_id"] for a in detail_response.json()["access_list"]]
        assert test_user not in access_users
        print(f"Verified {test_user} removed from access list")
    
    def test_revoke_access_viewer_denied(self):
        """DELETE /api/dashboard/projects/{id}/access/{user_id} - Viewer cannot revoke (403)"""
        response = requests.delete(
            f"{BASE_URL}/api/dashboard/projects/p-001/access/admin",
            headers={"Authorization": "Bearer mock-token-jane.smith"}
        )
        assert response.status_code == 403
        print("403 returned for viewer trying to revoke access")


class TestDataPersistence:
    """Tests for verifying data is persisted in MongoDB"""
    
    def test_user_last_login_persisted(self):
        """Verify user last_login timestamp is updated and persisted"""
        # Login twice and check last_login changes
        requests.post(f"{BASE_URL}/api/auth/login", json={"user_id": "admin"})
        
        response1 = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        login1 = response1.json().get("last_login")
        
        import time
        time.sleep(1)
        
        requests.post(f"{BASE_URL}/api/auth/login", json={"user_id": "admin"})
        response2 = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        login2 = response2.json().get("last_login")
        
        assert login2 is not None
        assert login1 != login2  # Timestamp should have changed
        print(f"Last login persisted: {login1} -> {login2}")
    
    def test_project_update_persisted(self):
        """Verify project updates are persisted to MongoDB"""
        # Create project
        response = requests.post(
            f"{BASE_URL}/api/dashboard/projects",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={
                "name": f"TEST_Persist_{uuid.uuid4().hex[:6]}",
                "source_erp": "quickbooks",
                "target_erp": "xero",
                "company_id": "acme-corp"
            }
        )
        project_id = response.json()["project"]["id"]
        
        # Update status
        requests.patch(
            f"{BASE_URL}/api/dashboard/projects/{project_id}",
            headers={"Authorization": "Bearer mock-token-admin"},
            json={"status": "in_progress"}
        )
        
        # Verify via fresh GET
        detail_response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/{project_id}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        assert detail_response.json()["status"] == "in_progress"
        print(f"Project status persisted to in_progress")
    
    def test_mapping_create_read_verify(self):
        """CREATE mappings -> GET to verify persisted in database"""
        unique_name = f"TEST_Persist_{uuid.uuid4().hex[:8]}"
        mappings = [
            {
                "source_account_name": unique_name,
                "source_account_type": "Bank",
                "target_account_name": "Persisted Bank",
                "target_account_type": "BANK",
                "confidence_score": 99.0,
                "status": "approved"
            }
        ]
        
        # Create
        requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/mappings",
            headers={"Authorization": "Bearer mock-token-john.doe"},
            json=mappings
        )
        
        # Read and verify
        response = requests.get(
            f"{BASE_URL}/api/dashboard/projects/p-001",
            headers={"Authorization": "Bearer mock-token-john.doe"}
        )
        project_mappings = response.json()["mappings"]
        mapping_names = [m["source_account_name"] for m in project_mappings]
        
        assert unique_name in mapping_names
        print(f"Mapping '{unique_name}' persisted and retrieved successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
