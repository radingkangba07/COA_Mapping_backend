"""
COA Migration API Backend Tests
Tests backend refactoring with microservices-ready structure
"""
import pytest
import requests
import os

# Get BASE URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://migrate-persist-db.preview.emergentagent.com"


class TestRootAndHealth:
    """Test root and health endpoints"""

    def test_root_endpoint_returns_version_2(self):
        """Root API endpoint returns version 2.0.0 and architecture info"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "version" in data, "Response should contain 'version'"
        assert data["version"] == "2.0.0", f"Expected version 2.0.0, got {data['version']}"
        assert "architecture" in data, "Response should contain 'architecture'"
        assert data["architecture"] == "microservices-ready", f"Expected 'microservices-ready', got {data['architecture']}"
        print(f"PASS: Root endpoint returns version {data['version']}, architecture: {data['architecture']}")

    def test_health_endpoint_returns_healthy(self):
        """Health check endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy", f"Expected status 'healthy', got {data.get('status')}"
        assert data.get("service") == "coa-migration-api", f"Expected service 'coa-migration-api', got {data.get('service')}"
        assert data.get("version") == "2.0.0", f"Expected version 2.0.0, got {data.get('version')}"
        print(f"PASS: Health endpoint returns healthy status with version 2.0.0")


class TestERPSystems:
    """Test ERP system endpoints"""

    def test_get_all_erp_systems_returns_6(self):
        """GET /api/erp-systems returns all 6 ERP systems"""
        response = requests.get(f"{BASE_URL}/api/erp-systems")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) == 6, f"Expected 6 ERP systems, got {len(data)}"
        
        # Verify all expected ERP systems are present
        erp_ids = [erp["id"] for erp in data]
        expected_ids = ["sap", "oracle_netsuite", "microsoft_dynamics", "quickbooks", "sage", "xero"]
        for expected_id in expected_ids:
            assert expected_id in erp_ids, f"Expected ERP '{expected_id}' not found"
        
        print(f"PASS: GET /api/erp-systems returns all 6 ERP systems: {erp_ids}")

    def test_get_sap_system_returns_8_fields(self):
        """GET /api/erp-systems/sap returns SAP system with 8 fields"""
        response = requests.get(f"{BASE_URL}/api/erp-systems/sap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("id") == "sap", f"Expected id 'sap', got {data.get('id')}"
        assert data.get("name") == "SAP", f"Expected name 'SAP', got {data.get('name')}"
        assert "fields" in data, "Response should contain 'fields'"
        assert isinstance(data["fields"], list), "Fields should be a list"
        assert len(data["fields"]) == 8, f"Expected 8 fields, got {len(data['fields'])}"
        
        # Verify field structure
        field_ids = [f["id"] for f in data["fields"]]
        expected_field_ids = ["account_number", "account_name", "account_type", "parent_account", 
                             "currency", "cost_center", "profit_center", "company_code"]
        for expected_field in expected_field_ids:
            assert expected_field in field_ids, f"Expected field '{expected_field}' not found"
        
        print(f"PASS: GET /api/erp-systems/sap returns SAP with {len(data['fields'])} fields")

    def test_get_nonexistent_erp_returns_404(self):
        """GET /api/erp-systems/nonexistent returns 404"""
        response = requests.get(f"{BASE_URL}/api/erp-systems/nonexistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: GET /api/erp-systems/nonexistent returns 404")


class TestAccountTypes:
    """Test account types endpoints"""

    def test_get_quickbooks_account_types_returns_15(self):
        """GET /api/account-types/quickbooks returns 15 account types"""
        response = requests.get(f"{BASE_URL}/api/account-types/quickbooks")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "account_types" in data, "Response should contain 'account_types'"
        assert isinstance(data["account_types"], list), "account_types should be a list"
        assert len(data["account_types"]) == 15, f"Expected 15 account types, got {len(data['account_types'])}"
        
        # Verify some expected types
        expected_types = ["Bank", "Accounts Receivable", "Fixed Assets", "Equity", "Income", "Expenses"]
        for expected_type in expected_types:
            assert expected_type in data["account_types"], f"Expected type '{expected_type}' not found"
        
        print(f"PASS: GET /api/account-types/quickbooks returns {len(data['account_types'])} types")

    def test_get_nonexistent_erp_account_types_returns_404(self):
        """GET /api/account-types/nonexistent returns 404"""
        response = requests.get(f"{BASE_URL}/api/account-types/nonexistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: GET /api/account-types/nonexistent returns 404")


class TestSampleData:
    """Test sample data endpoints"""

    def test_get_quickbooks_sample_data_returns_data_with_row_count(self):
        """GET /api/sample-data/quickbooks returns sample data with row count"""
        response = requests.get(f"{BASE_URL}/api/sample-data/quickbooks")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("erp_id") == "quickbooks", f"Expected erp_id 'quickbooks', got {data.get('erp_id')}"
        assert data.get("erp_name") == "QuickBooks", f"Expected erp_name 'QuickBooks', got {data.get('erp_name')}"
        assert "data" in data, "Response should contain 'data'"
        assert "row_count" in data, "Response should contain 'row_count'"
        assert isinstance(data["data"], list), "data should be a list"
        assert data["row_count"] == len(data["data"]), "row_count should match data length"
        assert data["row_count"] > 0, "Sample data should not be empty"
        
        # Verify sample data structure
        sample_row = data["data"][0]
        expected_keys = ["Number", "Name", "Type"]
        for key in expected_keys:
            assert key in sample_row, f"Sample row should contain '{key}'"
        
        print(f"PASS: GET /api/sample-data/quickbooks returns {data['row_count']} rows of sample data")

    def test_get_sap_sample_data(self):
        """GET /api/sample-data/sap returns SAP sample data"""
        response = requests.get(f"{BASE_URL}/api/sample-data/sap")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("erp_id") == "sap"
        assert data.get("row_count") > 0, "SAP should have sample data"
        print(f"PASS: GET /api/sample-data/sap returns {data['row_count']} rows")


class TestFuzzyMatch:
    """Test fuzzy matching endpoint"""

    def test_fuzzy_match_with_source_columns(self):
        """POST /api/fuzzy-match with source columns and target_erp performs matching"""
        payload = {
            "source_columns": ["Account Number", "Account Name", "Type", "Description"],
            "target_erp": "quickbooks",
            "threshold": 60
        }
        
        response = requests.post(
            f"{BASE_URL}/api/fuzzy-match",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "mappings" in data, "Response should contain 'mappings'"
        assert "target_fields" in data, "Response should contain 'target_fields'"
        assert isinstance(data["mappings"], list), "mappings should be a list"
        assert len(data["mappings"]) == 4, f"Expected 4 mappings, got {len(data['mappings'])}"
        
        # Verify mapping structure
        mapping = data["mappings"][0]
        required_keys = ["source_field", "target_field", "confidence", "method"]
        for key in required_keys:
            assert key in mapping, f"Mapping should contain '{key}'"
        
        print(f"PASS: POST /api/fuzzy-match returns {len(data['mappings'])} mappings with target fields")

    def test_fuzzy_match_nonexistent_target_erp_returns_404(self):
        """POST /api/fuzzy-match with nonexistent target_erp returns 404"""
        payload = {
            "source_columns": ["Account Number"],
            "target_erp": "nonexistent"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/fuzzy-match",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: POST /api/fuzzy-match with nonexistent target returns 404")


class TestHierarchicalMapping:
    """Test hierarchical mapping endpoint"""

    def test_hierarchical_mapping_creates_grouped_mappings(self):
        """POST /api/hierarchical-mapping creates grouped mappings by account type"""
        source_data = [
            {"Number": "1000", "Name": "Checking", "Type": "Bank"},
            {"Number": "1300", "Name": "Accounts Receivable", "Type": "Accounts Receivable"},
            {"Number": "4000", "Name": "Sales Revenue", "Type": "Income"},
            {"Number": "5000", "Name": "Cost of Goods", "Type": "Cost of Goods Sold"},
            {"Number": "6000", "Name": "Office Expenses", "Type": "Expenses"}
        ]
        
        payload = {"source_data": source_data}
        
        response = requests.post(
            f"{BASE_URL}/api/hierarchical-mapping?source_erp=quickbooks&target_erp=xero",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "grouped_mappings" in data, "Response should contain 'grouped_mappings'"
        assert "total_accounts" in data, "Response should contain 'total_accounts'"
        assert "total_types" in data, "Response should contain 'total_types'"
        
        assert isinstance(data["grouped_mappings"], list), "grouped_mappings should be a list"
        assert data["total_accounts"] == 5, f"Expected 5 total accounts, got {data['total_accounts']}"
        assert data["total_types"] >= 1, f"Expected at least 1 type, got {data['total_types']}"
        
        # Verify group structure
        group = data["grouped_mappings"][0]
        required_keys = ["source_type", "target_type", "accounts"]
        for key in required_keys:
            assert key in group, f"Group should contain '{key}'"
        
        assert isinstance(group["accounts"], list), "accounts should be a list"
        print(f"PASS: POST /api/hierarchical-mapping returns {data['total_types']} type groups with {data['total_accounts']} accounts")


class TestUploadAndExport:
    """Test file upload and export endpoints"""

    def test_upload_endpoint_exists(self):
        """POST /api/upload endpoint is accessible"""
        # Test with empty request to verify endpoint exists
        response = requests.post(f"{BASE_URL}/api/upload")
        # Should return 422 (validation error) or 400 (bad request) - not 404
        assert response.status_code in [400, 422], f"Expected 400 or 422, got {response.status_code}"
        print(f"PASS: POST /api/upload endpoint accessible (returns {response.status_code} for empty request)")

    def test_sessions_endpoint(self):
        """GET /api/sessions returns list of sessions"""
        response = requests.get(f"{BASE_URL}/api/sessions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/sessions returns {len(data)} sessions")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
