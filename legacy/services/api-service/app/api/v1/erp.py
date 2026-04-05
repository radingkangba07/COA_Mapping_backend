"""ERP system endpoints."""
import io
import pandas as pd
from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.erp import ERPSystem, ERPField, FuzzyMatchRequest, FuzzyMatchResponse
from app.services.erp_service import erp_service
from app.services.matching_service import matching_service

router = APIRouter(prefix="/erp-systems", tags=["ERP Systems"])


@router.get("", response_model=List[ERPSystem])
async def get_erp_systems():
    """Get all available ERP systems."""
    systems = erp_service.get_all_systems()
    return [
        ERPSystem(
            id=s["id"],
            name=s["name"],
            description=s["description"],
            fields=[ERPField(**f) for f in s["fields"]]
        )
        for s in systems
    ]


@router.get("/{erp_id}", response_model=ERPSystem)
async def get_erp_system(erp_id: str):
    """Get a specific ERP system by ID."""
    system = erp_service.get_system(erp_id)
    if not system:
        raise HTTPException(status_code=404, detail="ERP system not found")
    return ERPSystem(
        id=system["id"],
        name=system["name"],
        description=system["description"],
        fields=[ERPField(**f) for f in system["fields"]]
    )


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


@router.post("/fuzzy-match", response_model=FuzzyMatchResponse)
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
    
    return FuzzyMatchResponse(
        mappings=mappings,
        target_fields=[ERPField(**f) for f in target_fields]
    )
