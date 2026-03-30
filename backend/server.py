"""
COA Migration System - Backend Server

This server provides backward compatibility with the existing frontend
while using MongoDB for persistent data storage.

Architecture:
- Uses MongoDB for persistent storage via async motor driver
- Services are modularized in /app/backend/services
- Repository pattern for data access in /app/backend/repositories
- Object storage for file uploads (Emergent/R2/Spaces)
"""
import sys
import os
from pathlib import Path

# Add the api-service to Python path for existing services
_api_service_path = str(Path(__file__).parent.parent / 'services' / 'api-service')
sys.path.insert(0, _api_service_path)

from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query, Header, Response
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import uuid
from datetime import datetime, timezone
import pandas as pd
import io
from contextlib import asynccontextmanager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import from new service architecture (existing ERP and matching services)
from app.services.erp_service import erp_service
from app.services.matching_service import matching_service
from app.services.storage_service import storage_service, get_content_type

# Import new database layer
from db.connection import init_db, close_db, get_database, seed_initial_data
from services.auth_service import AuthService
from services.dashboard_service import DashboardService
from services.project_service import ProjectService
from services.storage_file_service import StorageFileService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting COA Migration API...")
    try:
        db = await init_db()
        # Seed initial data if database is empty
        await seed_initial_data(db)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down COA Migration API...")
    await close_db()


# Create the main app with lifespan
app = FastAPI(
    title="COA Migration System API",
    description="Chart of Accounts Migration Tool - MongoDB Persistent",
    version="2.1.0",
    lifespan=lifespan
)

# Create a router with the /api/v1 prefix
api_router = APIRouter(prefix="/api/v1")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_services():
    """Get initialized service instances."""
    db = get_database()
    return {
        "auth": AuthService(db),
        "dashboard": DashboardService(db),
        "project": ProjectService(db),
        "storage_file": StorageFileService(db)
    }


async def get_current_user_id(authorization: Optional[str]) -> str:
    """Extract and validate user_id from authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    services = get_services()
    user_id = services["auth"].extract_user_id_from_token(authorization)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Verify user exists
    user = await services["auth"].get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user_id


# ============================================================================
# SESSION DATA STORES (In-memory for file upload sessions only)
# ============================================================================

# These are temporary session stores for file processing - not persisted
uploaded_data_store: Dict[str, pd.DataFrame] = {}
session_store: Dict[str, Dict[str, Any]] = {}

# Storage initialization flag
storage_initialized = False


def init_storage():
    """Initialize object storage on first use."""
    global storage_initialized
    if not storage_initialized:
        try:
            storage_initialized = storage_service.init()
            if storage_initialized:
                logger.info("Object storage initialized successfully")
            else:
                logger.warning("Object storage not available - file operations will be limited")
        except Exception as e:
            logger.error(f"Failed to initialize storage: {e}")
            storage_initialized = False
    return storage_initialized


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class FieldMapping(BaseModel):
    source_field: str
    target_field: str
    confidence: float
    method: str


class FuzzyMatchRequest(BaseModel):
    source_columns: List[str]
    target_erp: str
    threshold: int = 60


class ManualMappingRequest(BaseModel):
    session_id: str
    mappings: List[FieldMapping]


class ExportRequest(BaseModel):
    session_id: str
    mappings: List[FieldMapping]


class HierarchicalMappingRequest(BaseModel):
    source_data: List[Dict[str, Any]]
    target_data: Optional[List[Dict[str, Any]]] = None


class UserLogin(BaseModel):
    user_id: str


class ProjectCreate(BaseModel):
    name: str
    source_erp: Optional[str] = ""
    target_erp: Optional[str] = ""
    company_id: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    current_step: int = Field(0, ge=0, le=5)


class ProjectAccessGrant(BaseModel):
    user_id: str
    permission: str = "viewer"


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@api_router.post("/auth/login")
async def login(data: UserLogin):
    """Login with user ID (mock authentication)."""
    services = get_services()
    result = await services["auth"].login(data.user_id)
    return result


@api_router.get("/auth/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current user from token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    services = get_services()
    user = await services["auth"].get_current_user(authorization)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return user


@api_router.post("/auth/logout")
async def logout():
    """Logout (mock implementation)."""
    return {"success": True, "message": "Logged out"}


# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

@api_router.get("/dashboard/companies")
async def get_user_companies(authorization: Optional[str] = Header(None)):
    """Get companies and projects accessible to the current user."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    return await services["dashboard"].get_user_companies(user_id)


@api_router.get("/dashboard/projects/{project_id}")
async def get_project_detail(
    project_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get detailed project information including saved mappings."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        result = await services["dashboard"].get_project_detail(project_id, user_id)
        if not result:
            raise HTTPException(status_code=404, detail="Project not found")
        result.setdefault("current_step", 0)
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.post("/dashboard/projects")
async def create_project(
    data: ProjectCreate,
    authorization: Optional[str] = Header(None)
):
    """Create a new project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    return await services["project"].create_project(
        name=data.name,
        source_erp=data.source_erp,
        target_erp=data.target_erp,
        company_id=data.company_id,
        created_by=user_id,
        description=data.description,
        company_name=data.company_name,
        current_step=data.current_step
    )


@api_router.patch("/dashboard/projects/{project_id}")
async def update_project(
    project_id: str,
    data: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Update project (status, mappings, etc.)."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        return await services["project"].update_project(project_id, user_id, data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@api_router.post("/dashboard/projects/{project_id}/mappings")
async def save_project_mappings(
    project_id: str,
    mappings: List[Dict[str, Any]],
    authorization: Optional[str] = Header(None)
):
    """Save mappings to a project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        return await services["project"].save_mappings(project_id, user_id, mappings)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.post("/dashboard/projects/{project_id}/access")
async def grant_project_access(
    project_id: str,
    data: ProjectAccessGrant,
    authorization: Optional[str] = Header(None)
):
    """Grant user access to a project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    # Check project exists
    db = get_database()
    from repositories.project_repository import ProjectRepository
    project_repo = ProjectRepository(db)
    project = await project_repo.find_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        return await services["project"].grant_access(
            project_id=project_id,
            requester_id=user_id,
            target_user_id=data.user_id,
            permission=data.permission
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.delete("/dashboard/projects/{project_id}/access/{target_user_id}")
async def revoke_project_access(
    project_id: str,
    target_user_id: str,
    authorization: Optional[str] = Header(None)
):
    """Revoke user access from a project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    # Check project exists
    db = get_database()
    from repositories.project_repository import ProjectRepository
    project_repo = ProjectRepository(db)
    project = await project_repo.find_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        return await services["project"].revoke_access(
            project_id=project_id,
            requester_id=user_id,
            target_user_id=target_user_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================================
# PROJECT CRUD ENDPOINTS (Frontend-facing)
# ============================================================================

@api_router.get("/projects")
async def list_projects(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    authorization: Optional[str] = Header(None)
):
    """List projects accessible to the current user with pagination."""
    user_id = await get_current_user_id(authorization)
    db = get_database()

    from repositories.project_access_repository import ProjectAccessRepository
    from repositories.project_repository import ProjectRepository
    access_repo = ProjectAccessRepository(db)
    project_repo = ProjectRepository(db)

    project_ids = await access_repo.get_user_project_ids(user_id)
    if not project_ids:
        return {"projects": [], "total": 0}

    query = {"id": {"$in": project_ids}}
    total = await project_repo.count(query)
    projects = await project_repo.find_many(
        query,
        sort=[("updated_at", -1)],
        skip=skip,
        limit=limit
    )

    for project in projects:
        project.setdefault("current_step", 0)

    return {"projects": projects, "total": total}


@api_router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get a single project by ID."""
    user_id = await get_current_user_id(authorization)
    db = get_database()

    from repositories.project_access_repository import ProjectAccessRepository
    from repositories.project_repository import ProjectRepository
    access_repo = ProjectAccessRepository(db)
    project_repo = ProjectRepository(db)

    access = await access_repo.find_user_access(user_id, project_id)
    if not access:
        raise HTTPException(status_code=403, detail="Access denied")

    project = await project_repo.find_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.setdefault("current_step", 0)

    return project


@api_router.post("/projects")
async def create_project_direct(
    data: ProjectCreate,
    authorization: Optional[str] = Header(None)
):
    """Create a new project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()

    result = await services["project"].create_project(
        name=data.name,
        source_erp=data.source_erp,
        target_erp=data.target_erp,
        company_id=data.company_id,
        created_by=user_id,
        description=data.description,
        company_name=data.company_name,
        current_step=data.current_step
    )

    return result["project"]


@api_router.patch("/projects/{project_id}")
async def update_project_direct(
    project_id: str,
    data: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Update a project (name, description, status)."""
    user_id = await get_current_user_id(authorization)
    services = get_services()

    try:
        result = await services["project"].update_project(project_id, user_id, data)
        return result["project"]
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@api_router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    authorization: Optional[str] = Header(None)
):
    """Delete a project and its access entries."""
    user_id = await get_current_user_id(authorization)
    db = get_database()

    from repositories.project_access_repository import ProjectAccessRepository
    from repositories.project_repository import ProjectRepository
    access_repo = ProjectAccessRepository(db)
    project_repo = ProjectRepository(db)

    access = await access_repo.find_user_access(user_id, project_id)
    if not access or access["permission"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete projects")

    project = await project_repo.find_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await access_repo.delete_project_access(project_id)
    await project_repo.delete_project(project_id)

    return {"status": "deleted"}


# ============================================================================
# FILE ENDPOINTS (Frontend-facing aliases for /storage/*)
# ============================================================================

@api_router.post("/files/upload")
async def upload_file_to_project(
    file: UploadFile = File(...),
    project_id: str = Query(..., description="Project to associate the file with"),
    file_type: str = Query(..., description="File type", pattern="^(sourcecoa|targetcoa|typemapping)$"),
    source_erp: str = Query(default="unknown"),
    target_erp: str = Query(default="unknown"),
    authorization: Optional[str] = Header(None)
):
    """Upload a file, persist it to storage linked to a project, and parse its contents."""
    user_id = await get_current_user_id(authorization)
    services = get_services()

    # Verify project access (editor+)
    if not await services["storage_file"].check_upload_permission(project_id, user_id):
        raise HTTPException(status_code=403, detail="Insufficient permissions to upload")

    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=400,
            detail="Only Excel (.xlsx, .xls) and CSV files are supported"
        )

    try:
        contents = await file.read()

        # Parse file into DataFrame
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        df.columns = df.columns.str.strip()

        # Create in-memory session (for immediate processing)
        session_id = str(uuid.uuid4())
        uploaded_data_store[session_id] = df
        session_store[session_id] = {
            "id": session_id,
            "source_erp": source_erp,
            "target_erp": target_erp,
            "file_name": file.filename,
            "source_columns": df.columns.tolist(),
            "row_count": len(df),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Persist to object storage + DB record
        file_record = None
        content_type = file.content_type or "application/octet-stream"
        if init_storage():
            result = storage_service.upload_file(
                data=contents,
                filename=file.filename,
                content_type=content_type,
                company_id="default",
                project_id=project_id,
                file_type=file_type,
            )
            file_record = await services["storage_file"].create_file_record(
                project_id=project_id,
                original_filename=file.filename,
                storage_path=result["path"],
                file_type=file_type,
                content_type=content_type,
                size_bytes=len(contents),
                company_id="default",
                uploaded_by=user_id,
                etag=result.get("etag"),
            )

        all_data = df.fillna("").to_dict(orient='records')

        return {
            "session_id": session_id,
            "file_name": file.filename,
            "columns": df.columns.tolist(),
            "row_count": len(df),
            "sample_data": all_data,
            "file": file_record,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@api_router.get("/files/{file_id}")
async def get_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get file metadata (frontend-facing alias for /storage/files/{file_id})."""
    return await get_file_metadata(file_id=file_id, authorization=authorization)


@api_router.get("/files/{file_id}/download")
async def download_project_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Download a file (frontend-facing alias for /storage/download/{file_id})."""
    return await download_file(file_id=file_id, authorization=authorization)


@api_router.get("/files/project/{project_id}")
async def list_files_for_project(
    project_id: str,
    file_type: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(None)
):
    """List files for a project (frontend-facing alias for /storage/project/{project_id}/files)."""
    return await list_project_files(
        project_id=project_id,
        file_type=file_type,
        authorization=authorization
    )


@api_router.delete("/files/{file_id}")
async def delete_project_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Delete a file (frontend-facing alias for /storage/files/{file_id})."""
    return await delete_file(file_id=file_id, authorization=authorization)


# ============================================================================
# MAPPING ENDPOINTS (Frontend-facing aliases)
# ============================================================================

@api_router.post("/mappings/hierarchical")
async def hierarchical_mapping_alias(
    request: HierarchicalMappingRequest,
    source_erp: str = Query(default="unknown"),
    target_erp: str = Query(default="unknown")
):
    """Frontend-facing alias for /hierarchical-mapping."""
    return await create_hierarchical_mapping(
        request=request, source_erp=source_erp, target_erp=target_erp
    )


@api_router.post("/mappings/project/{project_id}/export")
async def export_project_mappings(
    project_id: str,
    body: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """Export project mappings as Excel file."""
    mappings = body.get("mappings", [])

    mapped_data = {}
    for m in mappings:
        source = m.get("source_field", "")
        target = m.get("target_field", "")
        if source and target:
            if target not in mapped_data:
                mapped_data[target] = []
            mapped_data[target].append(source)

    rows = []
    for m in mappings:
        rows.append({
            "Source Field": m.get("source_field", ""),
            "Target Field": m.get("target_field", ""),
            "Source Type": m.get("source_type", ""),
            "Target Type": m.get("target_type", ""),
            "Confidence": m.get("confidence", 0),
            "Method": m.get("method", ""),
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Mapped COA')
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="mapped_coa_{project_id}.xlsx"'
        }
    )


# ============================================================================
# EXISTING API ROUTES (Legacy COA Mapping)
# ============================================================================

@api_router.get("/")
async def root():
    return {
        "message": "COA Migration System API",
        "version": "2.1.0",
        "architecture": "mongodb-persistent"
    }


@api_router.get("/erp-systems")
async def get_erp_systems():
    """Get all available ERP systems."""
    return erp_service.get_all_systems()


@api_router.get("/erp-systems/{erp_id}")
async def get_erp_system(erp_id: str):
    """Get a specific ERP system by ID."""
    system = erp_service.get_system(erp_id)
    if not system:
        raise HTTPException(status_code=404, detail="ERP system not found")
    return system


@api_router.get("/account-types/{target_erp}")
async def get_target_account_types(target_erp: str):
    """Get available account types for target ERP."""
    types = erp_service.get_account_types(target_erp)
    if not types:
        raise HTTPException(status_code=404, detail="Target ERP not found")
    return {"account_types": types}


@api_router.get("/sample-data/{erp_id}")
async def get_sample_data(erp_id: str):
    """Get sample COA data for a specific ERP system."""
    system = erp_service.get_system(erp_id)
    if not system:
        raise HTTPException(status_code=404, detail="ERP system not found")
    
    data = erp_service.get_sample_data(erp_id)
    return {
        "erp_id": erp_id,
        "erp_name": system["name"],
        "data": data,
        "row_count": len(data)
    }


@api_router.get("/sample-data/{erp_id}/download")
async def download_sample_data(erp_id: str):
    """Download sample COA data as Excel file."""
    system = erp_service.get_system(erp_id)
    if not system:
        raise HTTPException(status_code=404, detail="ERP system not found")
    
    data = erp_service.get_sample_data(erp_id)
    if not data:
        raise HTTPException(status_code=404, detail="No sample data available")
    
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='COA')
    output.seek(0)
    
    erp_name = system["name"].replace(" ", "_")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=sample_coa_{erp_name}.xlsx"
        }
    )


@api_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    source_erp: str = "unknown",
    target_erp: str = "unknown"
):
    """Upload an Excel file and parse its contents."""
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=400,
            detail="Only Excel (.xlsx, .xls) and CSV files are supported"
        )
    
    try:
        contents = await file.read()
        
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        df.columns = df.columns.str.strip()
        
        # Create session
        session_id = str(uuid.uuid4())
        
        # Store in memory (temporary for processing)
        uploaded_data_store[session_id] = df
        session_store[session_id] = {
            "id": session_id,
            "source_erp": source_erp,
            "target_erp": target_erp,
            "file_name": file.filename,
            "source_columns": df.columns.tolist(),
            "row_count": len(df),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        all_data = df.fillna("").to_dict(orient='records')
        
        return {
            "session_id": session_id,
            "file_name": file.filename,
            "columns": df.columns.tolist(),
            "row_count": len(df),
            "sample_data": all_data
        }
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@api_router.post("/fuzzy-match")
async def fuzzy_match(request: FuzzyMatchRequest):
    """Calculate fuzzy matches between source columns and target ERP fields."""
    system = erp_service.get_system(request.target_erp)
    if not system:
        raise HTTPException(status_code=404, detail="Target ERP system not found")
    
    target_fields = system["fields"]
    mappings = matching_service.calculate_fuzzy_matches(
        request.source_columns,
        target_fields,
        request.threshold
    )
    
    return {
        "mappings": mappings,
        "target_fields": target_fields
    }


@api_router.post("/hierarchical-mapping")
async def create_hierarchical_mapping(
    request: HierarchicalMappingRequest,
    source_erp: str = Query(default="unknown"),
    target_erp: str = Query(default="unknown")
):
    """Create hierarchical mapping grouped by account type."""
    result = matching_service.create_hierarchical_mapping(
        source_data=request.source_data,
        target_data=request.target_data,
        source_erp=source_erp,
        target_erp=target_erp
    )
    return result


@api_router.post("/save-mapping")
async def save_mapping(request: ManualMappingRequest):
    """Save manual mapping configuration."""
    if request.session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_store[request.session_id]["status"] = "mapped"
    
    return {
        "mapping_id": str(uuid.uuid4()),
        "status": "saved"
    }


@api_router.post("/export")
async def export_mapped_data(request: ExportRequest):
    """Export mapped data as Excel file."""
    if request.session_id not in uploaded_data_store:
        raise HTTPException(
            status_code=404,
            detail="Session data not found. Please re-upload the file."
        )
    
    df = uploaded_data_store[request.session_id]
    session = session_store.get(request.session_id, {})
    target_erp = session.get("target_erp", "unknown")
    
    system = erp_service.get_system(target_erp)
    target_fields = system.get("fields", []) if system else []
    
    mapped_data = {}
    for mapping in request.mappings:
        if mapping.target_field and mapping.source_field in df.columns:
            target_name = mapping.target_field
            for field in target_fields:
                if field["id"] == mapping.target_field:
                    target_name = field["name"]
                    break
            mapped_data[target_name] = df[mapping.source_field]
    
    mapped_df = pd.DataFrame(mapped_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        mapped_df.to_excel(writer, index=False, sheet_name='Mapped COA')
    output.seek(0)
    
    session_store[request.session_id]["status"] = "exported"
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=mapped_coa_{target_erp}.xlsx"
        }
    )


@api_router.get("/sessions")
async def get_sessions():
    """Get all migration sessions."""
    sessions = list(session_store.values())
    return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)[:100]


@api_router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_store[session_id]


@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a migration session."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del session_store[session_id]
    if session_id in uploaded_data_store:
        del uploaded_data_store[session_id]
    
    return {"status": "deleted"}


# ============================================================================
# STORAGE API ENDPOINTS
# ============================================================================

@api_router.post("/storage/upload")
async def upload_to_storage(
    file: UploadFile = File(...),
    project_id: str = Query(...),
    company_id: str = Query(default="default"),
    file_type: str = Query(default="upload"),
    job_id: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(None)
):
    """Upload a file to object storage."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    # Verify project access (editor+)
    if not await services["storage_file"].check_upload_permission(project_id, user_id):
        raise HTTPException(status_code=403, detail="Insufficient permissions to upload")
    
    # Initialize storage
    if not init_storage():
        raise HTTPException(status_code=503, detail="Storage service unavailable")
    
    try:
        # Read file content
        content = await file.read()
        content_type = file.content_type or get_content_type(file.filename)
        
        # Upload to object storage
        result = storage_service.upload_file(
            data=content,
            filename=file.filename,
            content_type=content_type,
            company_id=company_id,
            project_id=project_id,
            file_type=file_type,
            job_id=job_id
        )
        
        # Create file metadata record in database
        file_record = await services["storage_file"].create_file_record(
            project_id=project_id,
            original_filename=file.filename,
            storage_path=result["path"],
            file_type=file_type,
            content_type=content_type,
            size_bytes=len(content),
            company_id=company_id,
            job_id=job_id,
            uploaded_by=user_id,
            etag=result.get("etag")
        )
        
        return {
            "success": True,
            "file": file_record
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@api_router.get("/storage/files/{file_id}")
async def get_file_metadata(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Get file metadata by ID."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        file_meta = await services["storage_file"].get_file(file_id, user_id)
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
        return file_meta
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.get("/storage/download/{file_id}")
async def download_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Download a file from object storage."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        file_meta = await services["storage_file"].get_file(file_id, user_id)
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    # Initialize storage
    if not init_storage():
        raise HTTPException(status_code=503, detail="Storage service unavailable")
    
    try:
        storage_path = file_meta["storage_path"]
        content, content_type = storage_service.download_file(storage_path)
        
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_meta["original_filename"]}"',
                "Content-Length": str(len(content))
            }
        )
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@api_router.get("/storage/signed-url/{file_id}")
async def get_signed_url(
    file_id: str,
    expires_in: int = Query(default=3600, ge=60, le=86400),
    authorization: Optional[str] = Header(None)
):
    """Get a signed URL for direct file access."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        file_meta = await services["storage_file"].get_file(file_id, user_id)
        if not file_meta:
            raise HTTPException(status_code=404, detail="File not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    
    if not init_storage():
        raise HTTPException(status_code=503, detail="Storage service unavailable")
    
    storage_path = file_meta["storage_path"]
    signed_url = storage_service.get_download_url(storage_path, expires_in)
    
    return {
        "file_id": file_id,
        "signed_url": signed_url,
        "expires_in": expires_in if signed_url else None,
        "supported": signed_url is not None
    }


@api_router.get("/storage/project/{project_id}/files")
async def list_project_files(
    project_id: str,
    file_type: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(None)
):
    """List all files for a project."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        return await services["storage_file"].list_project_files(
            project_id=project_id,
            user_id=user_id,
            file_type=file_type
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@api_router.delete("/storage/files/{file_id}")
async def delete_file(
    file_id: str,
    authorization: Optional[str] = Header(None)
):
    """Soft delete a file."""
    user_id = await get_current_user_id(authorization)
    services = get_services()
    
    try:
        result = await services["storage_file"].delete_file(file_id, user_id)
        
        # Also delete from storage if possible
        if result["success"] and init_storage():
            file_meta = await services["storage_file"].get_file(file_id, user_id)
            if file_meta:
                try:
                    storage_service.delete_file(file_meta["storage_path"])
                except Exception as e:
                    logger.warning(f"Failed to delete from storage: {e}")
        
        return result
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@api_router.get("/health")
async def health_check():
    """Health check endpoint."""
    storage_status = "available" if storage_initialized else "unavailable"
    
    # Check DB connection
    try:
        db = get_database()
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "coa-migration-api",
        "version": "2.1.0",
        "architecture": "mongodb-persistent",
        "database": db_status,
        "storage": storage_status
    }


# ============================================================================
# INCLUDE ROUTER AND MIDDLEWARE
# ============================================================================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
