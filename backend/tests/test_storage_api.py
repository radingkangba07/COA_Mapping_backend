"""
COA Migration - Object Storage API Tests
Tests the storage endpoints for file upload, download, metadata, and access control.

Endpoints tested:
- POST /api/storage/upload - Upload file to object storage
- GET /api/storage/files/{file_id} - Get file metadata
- GET /api/storage/download/{file_id} - Download file content
- GET /api/storage/signed-url/{file_id} - Get signed URL (returns null for Emergent)
- GET /api/storage/project/{project_id}/files - List files for a project
- DELETE /api/storage/files/{file_id} - Delete a file (soft delete)
- GET /api/health - Verify storage status in health check

Access Control Tests:
- Viewers cannot upload files (403)
- Download respects project permissions
- Delete requires editor or above

Storage Path Tests:
- Verify path follows key structure: {app}/company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}
"""
import pytest
import requests
import os
import uuid

# Get BASE URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://migrate-persist-db.preview.emergentagent.com"


# Test users and their tokens
# admin - has admin on p-001, p-002, p-003
# john.doe - has admin on p-001, p-002
# jane.smith - has viewer on p-001, admin on p-003


class TestHealthCheckStorage:
    """Test /api/health endpoint for storage status"""
    
    def test_health_check_includes_storage_status(self):
        """GET /api/health returns storage status field"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "healthy"
        assert "storage" in data, "Health check should include 'storage' field"
        # Storage status can be 'available' or 'unavailable'
        assert data["storage"] in ["available", "unavailable"], f"Storage status should be 'available' or 'unavailable', got {data['storage']}"
        
        print(f"PASS: Health check returns storage status: {data['storage']}")


class TestStorageUpload:
    """Test POST /api/storage/upload endpoint"""
    
    def test_upload_file_success(self):
        """POST /api/storage/upload uploads file and returns metadata"""
        # Create a simple test file content
        test_content = b"Test file content for storage upload test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp",
                "file_type": "upload"
            },
            files={
                "file": ("TEST_test_upload.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert "file" in data, "Response should contain 'file' metadata"
        
        file_meta = data["file"]
        
        # Verify required fields
        assert "id" in file_meta, "File metadata should have 'id'"
        assert "storage_path" in file_meta, "File metadata should have 'storage_path'"
        assert "original_filename" in file_meta, "File metadata should have 'original_filename'"
        assert "content_type" in file_meta, "File metadata should have 'content_type'"
        assert "size_bytes" in file_meta, "File metadata should have 'size_bytes'"
        assert "project_id" in file_meta, "File metadata should have 'project_id'"
        assert "company_id" in file_meta, "File metadata should have 'company_id'"
        assert "uploaded_by" in file_meta, "File metadata should have 'uploaded_by'"
        
        # Verify values
        assert file_meta["original_filename"] == "TEST_test_upload.txt"
        assert file_meta["project_id"] == "p-001"
        assert file_meta["company_id"] == "acme-corp"
        assert file_meta["size_bytes"] == len(test_content)
        assert file_meta["uploaded_by"] == "admin"
        
        # Verify storage path follows expected structure
        # Path should be: {app}/company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}
        path = file_meta["storage_path"]
        assert "/company/acme-corp/" in path, f"Storage path should include company_id: {path}"
        assert "/project/p-001/" in path, f"Storage path should include project_id: {path}"
        assert "/uploads/" in path, f"Storage path should include 'uploads' for upload type: {path}"
        assert path.endswith(".txt"), f"Storage path should end with original extension: {path}"
        
        print(f"PASS: Uploaded file with id={file_meta['id']}, path={path}")
        return file_meta["id"]
    
    def test_upload_file_with_job_id(self):
        """POST /api/storage/upload with job_id creates job-specific path"""
        test_content = b"Job-specific file content"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp",
                "file_type": "upload",
                "job_id": "job-123"
            },
            files={
                "file": ("TEST_job_file.csv", test_content, "text/csv")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        file_meta = data["file"]
        
        # Verify job_id is stored
        assert file_meta.get("job_id") == "job-123", f"Expected job_id='job-123', got {file_meta.get('job_id')}"
        
        # Verify path includes jobs/{job_id}/
        path = file_meta["storage_path"]
        assert "/jobs/job-123/" in path, f"Storage path should include jobs/job_id when job_id provided: {path}"
        
        print(f"PASS: Uploaded job-specific file with job_id, path={path}")
    
    def test_upload_file_artifact_type(self):
        """POST /api/storage/upload with file_type=artifact uses artifacts folder"""
        test_content = b"Artifact file content"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp",
                "file_type": "artifact"
            },
            files={
                "file": ("TEST_artifact.xlsx", test_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        path = data["file"]["storage_path"]
        
        # Artifact files should be in /artifacts/ folder
        assert "/artifacts/" in path, f"Artifact file should be in artifacts folder: {path}"
        
        print(f"PASS: Uploaded artifact file with path={path}")
    
    def test_upload_without_auth_fails(self):
        """POST /api/storage/upload without auth returns 401"""
        test_content = b"Unauthorized upload test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={"project_id": "p-001"},
            files={"file": ("test.txt", test_content, "text/plain")}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Upload without auth returns 401")
    
    def test_viewer_cannot_upload(self):
        """POST /api/storage/upload by viewer returns 403"""
        test_content = b"Viewer upload test"
        
        # jane.smith has viewer permission on p-001
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={"file": ("test.txt", test_content, "text/plain")},
            headers={
                "Authorization": "Bearer mock-token-jane.smith"
            }
        )
        
        assert response.status_code == 403, f"Expected 403 for viewer upload, got {response.status_code}"
        print(f"PASS: Viewer cannot upload files (403)")
    
    def test_upload_with_default_company(self):
        """POST /api/storage/upload with default company_id"""
        test_content = b"Default company test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001"
                # company_id defaults to "default"
            },
            files={"file": ("TEST_default_company.txt", test_content, "text/plain")},
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        file_meta = data["file"]
        
        # Default company_id should be "default"
        assert file_meta["company_id"] == "default", f"Expected company_id='default', got {file_meta['company_id']}"
        
        print(f"PASS: Upload with default company_id works")


class TestStorageGetFileMetadata:
    """Test GET /api/storage/files/{file_id} endpoint"""
    
    @pytest.fixture
    def uploaded_file_id(self):
        """Upload a test file and return its ID"""
        test_content = b"Test file for metadata retrieval"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_metadata_test.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        return response.json()["file"]["id"]
    
    def test_get_file_metadata_success(self, uploaded_file_id):
        """GET /api/storage/files/{file_id} returns file metadata"""
        response = requests.get(
            f"{BASE_URL}/api/storage/files/{uploaded_file_id}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        file_meta = response.json()
        
        # Verify required fields
        assert file_meta["id"] == uploaded_file_id
        assert "storage_path" in file_meta
        assert "original_filename" in file_meta
        assert "content_type" in file_meta
        assert "size_bytes" in file_meta
        assert "project_id" in file_meta
        assert "company_id" in file_meta
        assert "created_at" in file_meta
        
        print(f"PASS: Got file metadata for {uploaded_file_id}")
    
    def test_get_file_metadata_not_found(self):
        """GET /api/storage/files/nonexistent returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/storage/files/nonexistent-file-id",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: File not found returns 404")
    
    def test_get_file_metadata_without_auth(self, uploaded_file_id):
        """GET /api/storage/files/{file_id} without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/storage/files/{uploaded_file_id}")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Get file metadata without auth returns 401")


class TestStorageDownload:
    """Test GET /api/storage/download/{file_id} endpoint"""
    
    @pytest.fixture
    def uploaded_file(self):
        """Upload a test file and return its ID and content"""
        test_content = b"Download test content - unique identifier: " + uuid.uuid4().hex.encode()
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_download_test.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        return {
            "id": response.json()["file"]["id"],
            "content": test_content
        }
    
    def test_download_file_success(self, uploaded_file):
        """GET /api/storage/download/{file_id} returns file content"""
        response = requests.get(
            f"{BASE_URL}/api/storage/download/{uploaded_file['id']}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify content matches
        assert response.content == uploaded_file["content"], "Downloaded content should match uploaded content"
        
        # Verify headers - Content-Disposition should always be present
        # Note: Content-Length may be converted to Transfer-Encoding: chunked by proxies
        assert "Content-Disposition" in response.headers
        
        print(f"PASS: Downloaded file content matches original")
    
    def test_download_file_not_found(self):
        """GET /api/storage/download/nonexistent returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/storage/download/nonexistent-file-id",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: Download nonexistent file returns 404")
    
    def test_download_without_auth(self, uploaded_file):
        """GET /api/storage/download/{file_id} without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/storage/download/{uploaded_file['id']}")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Download without auth returns 401")
    
    def test_viewer_can_download(self, uploaded_file):
        """GET /api/storage/download/{file_id} - viewer can download"""
        # jane.smith has viewer permission on p-001
        response = requests.get(
            f"{BASE_URL}/api/storage/download/{uploaded_file['id']}",
            headers={"Authorization": "Bearer mock-token-jane.smith"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"PASS: Viewer can download files")


class TestStorageSignedUrl:
    """Test GET /api/storage/signed-url/{file_id} endpoint"""
    
    @pytest.fixture
    def uploaded_file_id(self):
        """Upload a test file and return its ID"""
        test_content = b"Signed URL test content"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_signed_url_test.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        return response.json()["file"]["id"]
    
    def test_signed_url_returns_null_for_emergent(self, uploaded_file_id):
        """GET /api/storage/signed-url/{file_id} returns null for Emergent provider"""
        response = requests.get(
            f"{BASE_URL}/api/storage/signed-url/{uploaded_file_id}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "file_id" in data, "Response should have file_id"
        assert data["file_id"] == uploaded_file_id
        
        # For Emergent provider, signed_url should be null and supported should be false
        assert data.get("signed_url") is None, f"Expected signed_url=null for Emergent, got {data.get('signed_url')}"
        assert data.get("supported") == False, f"Expected supported=False for Emergent, got {data.get('supported')}"
        
        print(f"PASS: Signed URL returns null for Emergent provider (signed_url=null, supported=false)")
    
    def test_signed_url_file_not_found(self):
        """GET /api/storage/signed-url/nonexistent returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/storage/signed-url/nonexistent-file-id",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: Signed URL for nonexistent file returns 404")
    
    def test_signed_url_without_auth(self, uploaded_file_id):
        """GET /api/storage/signed-url/{file_id} without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/storage/signed-url/{uploaded_file_id}")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Signed URL without auth returns 401")


class TestStorageListProjectFiles:
    """Test GET /api/storage/project/{project_id}/files endpoint"""
    
    @pytest.fixture
    def uploaded_files(self):
        """Upload multiple test files to a project"""
        file_ids = []
        
        for i in range(3):
            test_content = f"Project file {i} content".encode()
            response = requests.post(
                f"{BASE_URL}/api/storage/upload",
                params={
                    "project_id": "p-001",
                    "company_id": "acme-corp",
                    "file_type": "upload" if i < 2 else "artifact"
                },
                files={
                    "file": (f"TEST_project_file_{i}.txt", test_content, "text/plain")
                },
                headers={
                    "Authorization": "Bearer mock-token-admin"
                }
            )
            
            assert response.status_code == 200
            file_ids.append(response.json()["file"]["id"])
        
        return file_ids
    
    def test_list_project_files_success(self, uploaded_files):
        """GET /api/storage/project/{project_id}/files returns files list"""
        response = requests.get(
            f"{BASE_URL}/api/storage/project/p-001/files",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "project_id" in data
        assert data["project_id"] == "p-001"
        assert "files" in data
        assert "total" in data
        
        files = data["files"]
        assert isinstance(files, list)
        assert data["total"] >= len(uploaded_files), f"Expected at least {len(uploaded_files)} files, got {data['total']}"
        
        # Verify uploaded files are in the list
        file_ids_in_list = [f["id"] for f in files]
        for file_id in uploaded_files:
            assert file_id in file_ids_in_list, f"Uploaded file {file_id} should be in list"
        
        print(f"PASS: Listed {data['total']} files for project p-001")
    
    def test_list_project_files_filter_by_type(self, uploaded_files):
        """GET /api/storage/project/{project_id}/files?file_type=upload filters by type"""
        response = requests.get(
            f"{BASE_URL}/api/storage/project/p-001/files",
            params={"file_type": "upload"},
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        files = data["files"]
        
        # All returned files should be of type "upload"
        for f in files:
            assert f.get("file_type") == "upload", f"Expected file_type='upload', got {f.get('file_type')}"
        
        print(f"PASS: File type filter works - got {len(files)} upload files")
    
    def test_list_project_files_without_auth(self):
        """GET /api/storage/project/{project_id}/files without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/storage/project/p-001/files")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: List files without auth returns 401")
    
    def test_list_project_files_no_access(self):
        """GET /api/storage/project/{project_id}/files for user without access returns 403"""
        # Create new user with no access
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": "TEST_no_access_user"},
            headers={"Content-Type": "application/json"}
        )
        
        response = requests.get(
            f"{BASE_URL}/api/storage/project/p-001/files",
            headers={"Authorization": "Bearer mock-token-test_no_access_user"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print(f"PASS: User without project access cannot list files (403)")


class TestStorageDeleteFile:
    """Test DELETE /api/storage/files/{file_id} endpoint"""
    
    @pytest.fixture
    def uploaded_file_id(self):
        """Upload a test file and return its ID"""
        test_content = b"Delete test content"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_delete_test.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        return response.json()["file"]["id"]
    
    def test_delete_file_success(self, uploaded_file_id):
        """DELETE /api/storage/files/{file_id} soft deletes file"""
        response = requests.delete(
            f"{BASE_URL}/api/storage/files/{uploaded_file_id}",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("message") == "File deleted"
        
        # Verify file is soft-deleted - list should not include it
        list_response = requests.get(
            f"{BASE_URL}/api/storage/project/p-001/files",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        files = list_response.json()["files"]
        file_ids = [f["id"] for f in files]
        assert uploaded_file_id not in file_ids, "Deleted file should not appear in list"
        
        print(f"PASS: File {uploaded_file_id} soft deleted")
    
    def test_delete_file_not_found(self):
        """DELETE /api/storage/files/nonexistent returns 404"""
        response = requests.delete(
            f"{BASE_URL}/api/storage/files/nonexistent-file-id",
            headers={"Authorization": "Bearer mock-token-admin"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"PASS: Delete nonexistent file returns 404")
    
    def test_delete_file_without_auth(self, uploaded_file_id):
        """DELETE /api/storage/files/{file_id} without auth returns 401"""
        response = requests.delete(f"{BASE_URL}/api/storage/files/{uploaded_file_id}")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"PASS: Delete without auth returns 401")
    
    def test_viewer_cannot_delete(self, uploaded_file_id):
        """DELETE /api/storage/files/{file_id} by viewer returns 403"""
        # jane.smith has viewer permission on p-001
        response = requests.delete(
            f"{BASE_URL}/api/storage/files/{uploaded_file_id}",
            headers={"Authorization": "Bearer mock-token-jane.smith"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print(f"PASS: Viewer cannot delete files (403)")


class TestStoragePathStructure:
    """Test storage path follows expected key structure"""
    
    def test_path_structure_upload_type(self):
        """Verify upload file path follows: {app}/company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}"""
        test_content = b"Path structure test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-002",
                "company_id": "globex-inc",
                "file_type": "upload"
            },
            files={
                "file": ("TEST_path_test.xlsx", test_content, "application/vnd.ms-excel")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        
        path = response.json()["file"]["storage_path"]
        
        # Verify path components
        assert path.startswith("coa-migration/"), f"Path should start with app name: {path}"
        assert "/company/globex-inc/" in path, f"Path should include /company/{company_id}/: {path}"
        assert "/project/p-002/" in path, f"Path should include /project/{project_id}/: {path}"
        assert "/uploads/" in path, f"Path should include /uploads/ for upload type: {path}"
        assert path.endswith(".xlsx"), f"Path should end with original extension: {path}"
        
        # Verify UUID in filename
        filename = path.split("/")[-1]
        uuid_part = filename.rsplit(".", 1)[0]
        try:
            uuid.UUID(uuid_part)
        except ValueError:
            pytest.fail(f"Filename should contain UUID: {filename}")
        
        print(f"PASS: Upload path follows expected structure: {path}")
    
    def test_path_structure_artifact_type(self):
        """Verify artifact file path includes /artifacts/"""
        test_content = b"Artifact path test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp",
                "file_type": "artifact"
            },
            files={
                "file": ("TEST_artifact.pdf", test_content, "application/pdf")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        
        path = response.json()["file"]["storage_path"]
        assert "/artifacts/" in path, f"Artifact path should include /artifacts/: {path}"
        assert path.endswith(".pdf"), f"Path should preserve original extension: {path}"
        
        print(f"PASS: Artifact path structure correct: {path}")
    
    def test_path_structure_job_type(self):
        """Verify job file path includes /jobs/{job_id}/"""
        test_content = b"Job path test"
        
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp",
                "file_type": "upload",
                "job_id": "migration-job-456"
            },
            files={
                "file": ("TEST_job_output.json", test_content, "application/json")
            },
            headers={
                "Authorization": "Bearer mock-token-admin"
            }
        )
        
        assert response.status_code == 200
        
        path = response.json()["file"]["storage_path"]
        assert "/jobs/migration-job-456/" in path, f"Job path should include /jobs/{{job_id}}/: {path}"
        assert path.endswith(".json"), f"Path should preserve original extension: {path}"
        
        print(f"PASS: Job path structure correct: {path}")


class TestStorageAccessControl:
    """Test storage access control based on project permissions"""
    
    def test_editor_can_upload(self):
        """Editor can upload files to project"""
        # First grant editor access to a test user
        test_user = f"test_editor_{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": test_user}
        )
        
        # Admin grants editor access
        requests.post(
            f"{BASE_URL}/api/dashboard/projects/p-001/access",
            json={"user_id": test_user, "permission": "editor"},
            headers={
                "Authorization": "Bearer mock-token-admin",
                "Content-Type": "application/json"
            }
        )
        
        # Editor uploads file
        test_content = b"Editor upload test"
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_editor_upload.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": f"Bearer mock-token-{test_user.lower()}"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"PASS: Editor can upload files")
    
    def test_no_project_access_cannot_upload(self):
        """User without project access cannot upload"""
        # Create new user without access
        test_user = f"test_noaccess_{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"user_id": test_user}
        )
        
        test_content = b"No access upload test"
        response = requests.post(
            f"{BASE_URL}/api/storage/upload",
            params={
                "project_id": "p-001",
                "company_id": "acme-corp"
            },
            files={
                "file": ("TEST_noaccess.txt", test_content, "text/plain")
            },
            headers={
                "Authorization": f"Bearer mock-token-{test_user.lower()}"
            }
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print(f"PASS: User without project access cannot upload (403)")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
