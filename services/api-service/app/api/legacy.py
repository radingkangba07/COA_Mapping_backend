"""Legacy API endpoints for backward compatibility with existing frontend.

This module provides the same API interface as the original monolithic server.py
to ensure the existing frontend continues to work without modifications.

These endpoints will be deprecated once the frontend is updated to use the
new v1 API with async job flow.
"""
import io
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import pandas as pd

from app.services.erp_service import erp_service
from app.services.matching_service import matching_service

router = APIRouter()

# In-memory storage for backward compatibility
# This will be replaced by database storage
uploaded_data_store: Dict[str, pd.DataFrame] = {}
session_store: Dict[str, Dict[str, Any]] = {}


# Legacy Pydantic models
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


@router.get("/")
async def root():
    """Root endpoint."""
    return {"message": "COA Migration System API"}


@router.get("/erp-systems")
async def get_erp_systems():
    """Get all available ERP systems."""
    return erp_service.get_all_systems()


@router.get("/erp-systems/{erp_id}")
async def get_erp_system(erp_id: str):
    """Get a specific ERP system by ID."""
    system = erp_service.get_system(erp_id)
    if not system:
        raise HTTPException(status_code=404, detail="ERP system not found")
    return system


@router.get("/account-types/{target_erp}")
async def get_target_account_types(target_erp: str):
    """Get available account types for target ERP."""
    types = erp_service.get_account_types(target_erp)
    if not types:
        raise HTTPException(status_code=404, detail="Target ERP not found")
    return {"account_types": types}


@router.get("/sample-data/{erp_id}")
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


@router.get("/sample-data/{erp_id}/download")
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


@router.post("/upload")
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
        
        # Store in memory
        uploaded_data_store[session_id] = df
        session_store[session_id] = {
            "id": session_id,
            "source_erp": source_erp,
            "target_erp": target_erp,
            "file_name": file.filename,
            "source_columns": df.columns.tolist(),
            "row_count": len(df),
            "status": "pending"
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
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/fuzzy-match")
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


@router.post("/hierarchical-mapping")
async def create_hierarchical_mapping(
    request: HierarchicalMappingRequest,
    source_erp: str = Query(default="unknown"),
    target_erp: str = Query(default="unknown")
):
    """Create hierarchical mapping grouped by account type with auto-populated target names."""
    result = matching_service.create_hierarchical_mapping(
        source_data=request.source_data,
        target_data=request.target_data,
        source_erp=source_erp,
        target_erp=target_erp
    )
    return result


@router.post("/save-mapping")
async def save_mapping(request: ManualMappingRequest):
    """Save manual mapping configuration."""
    if request.session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update session status
    session_store[request.session_id]["status"] = "mapped"
    
    return {
        "mapping_id": str(uuid.uuid4()),
        "status": "saved"
    }


@router.post("/export")
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
    
    # Create mapped DataFrame
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


@router.get("/sessions")
async def get_sessions():
    """Get all migration sessions."""
    sessions = list(session_store.values())
    return sorted(sessions, key=lambda x: x.get("id", ""), reverse=True)[:100]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_store[session_id]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a migration session."""
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    del session_store[session_id]
    if session_id in uploaded_data_store:
        del uploaded_data_store[session_id]
    
    return {"status": "deleted"}


# Alias for backward compatibility
legacy_router = router
