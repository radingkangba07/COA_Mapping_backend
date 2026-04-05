# Object Storage Integration

This document describes the object storage integration for the COA Migration System.

## Overview

The application supports multiple storage providers through a unified, provider-agnostic interface:

1. **Emergent Object Storage** (default) - Uses your existing EMERGENT_LLM_KEY
2. **Cloudflare R2** - S3-compatible object storage
3. **DigitalOcean Spaces** - S3-compatible object storage

## Key Structure

Files are organized in a hierarchical structure:

```
{app_name}/company/{company_id}/project/{project_id}/uploads/{uuid}.{ext}
{app_name}/company/{company_id}/project/{project_id}/artifacts/{uuid}.{ext}
{app_name}/company/{company_id}/project/{project_id}/jobs/{job_id}/{uuid}.{ext}
```

Example:
```
coa-migration/company/acme-corp/project/p-001/uploads/abc123.xlsx
coa-migration/company/acme-corp/project/p-001/artifacts/def456.xlsx
coa-migration/company/acme-corp/project/p-001/jobs/job-789/ghi012.csv
```

## Configuration

### Option 1: Emergent Object Storage (Default)

No additional configuration needed! The storage uses your existing `EMERGENT_LLM_KEY`.

```env
STORAGE_PROVIDER=emergent
EMERGENT_LLM_KEY=your-key-here
```

### Option 2: Cloudflare R2

```env
STORAGE_PROVIDER=r2
S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
S3_ACCESS_KEY=your-r2-access-key
S3_SECRET_KEY=your-r2-secret-key
S3_BUCKET=coa-storage
S3_REGION=auto
```

### Option 3: DigitalOcean Spaces

```env
STORAGE_PROVIDER=spaces
S3_ENDPOINT=https://nyc3.digitaloceanspaces.com
S3_ACCESS_KEY=your-spaces-access-key
S3_SECRET_KEY=your-spaces-secret-key
S3_BUCKET=coa-storage
S3_REGION=nyc3
```

## API Endpoints

### Upload File

```http
POST /api/storage/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

Query Parameters:
- project_id (required): Project ID
- company_id (optional): Company ID (default: "default")
- file_type (optional): "upload", "artifact", "export" (default: "upload")
- job_id (optional): Job ID for job-specific files

Response:
{
  "success": true,
  "file": {
    "id": "file-uuid",
    "storage_path": "coa-migration/company/.../uploads/abc.xlsx",
    "original_filename": "report.xlsx",
    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "size_bytes": 12345
  }
}
```

### Get File Metadata

```http
GET /api/storage/files/{file_id}
Authorization: Bearer {token}

Response:
{
  "id": "file-uuid",
  "project_id": "p-001",
  "company_id": "acme-corp",
  "original_filename": "report.xlsx",
  "content_type": "...",
  "size_bytes": 12345,
  "status": "uploaded",
  "created_at": "2024-03-15T10:30:00Z"
}
```

### Download File

```http
GET /api/storage/download/{file_id}
Authorization: Bearer {token}

Response: Binary file content with appropriate headers
```

### Get Signed URL (R2/Spaces only)

```http
GET /api/storage/signed-url/{file_id}?expires_in=3600
Authorization: Bearer {token}

Response:
{
  "file_id": "file-uuid",
  "signed_url": "https://...",
  "expires_in": 3600,
  "supported": true
}
```

Note: Emergent storage returns `signed_url: null, supported: false`

### List Project Files

```http
GET /api/storage/project/{project_id}/files?file_type=upload
Authorization: Bearer {token}

Response:
{
  "project_id": "p-001",
  "files": [...],
  "total": 5
}
```

### Delete File

```http
DELETE /api/storage/files/{file_id}
Authorization: Bearer {token}

Response:
{
  "success": true,
  "message": "File deleted"
}
```

## Access Control

- File operations respect existing project access permissions
- **Viewers** can only download files
- **Editors** and above can upload and delete files
- Files are linked to `project_id` for access verification

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend  │────▶│  Backend API     │────▶│ Storage Service │
│             │     │  /api/storage/*  │     │ (Abstraction)   │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                            ┌─────────────────────────┼─────────────────────────┐
                            │                         │                         │
                    ┌───────▼───────┐         ┌───────▼───────┐         ┌───────▼───────┐
                    │   Emergent    │         │ Cloudflare R2 │         │  DO Spaces    │
                    │   Storage     │         │ (S3 API)      │         │  (S3 API)     │
                    └───────────────┘         └───────────────┘         └───────────────┘
```

## Files Modified/Created

### Created
- `/app/services/api-service/app/services/storage_service.py` - Storage abstraction layer
- `/app/backend/.env.storage.example` - Configuration example
- `/app/docs/STORAGE.md` - This documentation

### Modified
- `/app/backend/server.py` - Added storage endpoints
- `/app/services/api-service/app/models/file.py` - Updated with storage fields
- `/app/services/api-service/app/services/__init__.py` - Export storage service

## Assumptions

1. **Default Provider**: Emergent Object Storage (no additional setup needed)
2. **File Metadata**: Stored in-memory (migrate to PostgreSQL in production)
3. **Soft Delete**: Files are marked as deleted but not removed from storage
4. **Access Control**: Uses existing project permissions
5. **Signed URLs**: Only available for R2/Spaces (not Emergent)

## Switching Providers

To switch providers, only change environment variables - no code changes needed:

```bash
# Switch to Cloudflare R2
export STORAGE_PROVIDER=r2
export S3_ENDPOINT=https://...
# ... other S3 settings

# Restart the backend
sudo supervisorctl restart backend
```
