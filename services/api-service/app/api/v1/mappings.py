"""Mapping management endpoints."""
import io
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.core.database import get_db
from app.models.project import Project
from app.models.mapping import Mapping, MappingStatus
from app.schemas.mapping import (
    MappingCreate,
    MappingUpdate,
    MappingResponse,
    MappingBulkUpdate,
    HierarchicalMappingRequest,
    HierarchicalMappingResponse
)
from app.services.erp_service import erp_service
from app.services.matching_service import matching_service

router = APIRouter(prefix="/mappings", tags=["Mappings"])


@router.post("/hierarchical", response_model=HierarchicalMappingResponse)
async def create_hierarchical_mapping(
    request: HierarchicalMappingRequest,
    source_erp: str = Query(default="unknown"),
    target_erp: str = Query(default="unknown")
):
    """Create hierarchical mapping grouped by account type.
    
    This is a synchronous operation for smaller datasets.
    For large datasets, create a job instead.
    """
    result = matching_service.create_hierarchical_mapping(
        source_data=request.source_data,
        target_data=request.target_data,
        source_erp=source_erp,
        target_erp=target_erp
    )
    return HierarchicalMappingResponse(**result)


@router.post("", response_model=MappingResponse, status_code=201)
async def create_mapping(
    mapping_data: MappingCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a single mapping."""
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == mapping_data.project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    
    mapping = Mapping(**mapping_data.model_dump())
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return MappingResponse.model_validate(mapping)


@router.post("/bulk", response_model=List[MappingResponse], status_code=201)
async def create_mappings_bulk(
    mappings_data: List[MappingCreate],
    db: AsyncSession = Depends(get_db)
):
    """Create multiple mappings in bulk."""
    if not mappings_data:
        return []
    
    # Verify project exists (assuming all mappings are for same project)
    project_id = mappings_data[0].project_id
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")
    
    mappings = [Mapping(**m.model_dump()) for m in mappings_data]
    db.add_all(mappings)
    await db.commit()
    
    for m in mappings:
        await db.refresh(m)
    
    return [MappingResponse.model_validate(m) for m in mappings]


@router.get("/project/{project_id}", response_model=List[MappingResponse])
async def get_project_mappings(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, le=10000),
    db: AsyncSession = Depends(get_db)
):
    """Get all mappings for a project."""
    query = select(Mapping).where(Mapping.project_id == project_id)
    
    if status:
        query = query.where(Mapping.status == status)
    if source_type:
        query = query.where(Mapping.source_account_type == source_type)
    
    query = query.order_by(
        Mapping.source_account_type,
        Mapping.source_account_name
    ).offset(skip).limit(limit)
    
    result = await db.execute(query)
    mappings = result.scalars().all()
    
    return [MappingResponse.model_validate(m) for m in mappings]


@router.get("/{mapping_id}", response_model=MappingResponse)
async def get_mapping(
    mapping_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific mapping."""
    result = await db.execute(
        select(Mapping).where(Mapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return MappingResponse.model_validate(mapping)


@router.patch("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: uuid.UUID,
    update_data: MappingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a mapping (e.g., user approval or modification)."""
    result = await db.execute(
        select(Mapping).where(Mapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(mapping, key, value)
    
    # Mark as user-modified
    if "remark" not in update_dict:
        mapping.remark = "user"
    
    await db.commit()
    await db.refresh(mapping)
    return MappingResponse.model_validate(mapping)


@router.post("/bulk-update", response_model=int)
async def update_mappings_bulk(
    bulk_update: MappingBulkUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update multiple mappings at once."""
    if not bulk_update.mapping_ids:
        return 0
    
    update_dict = bulk_update.updates.model_dump(exclude_unset=True)
    if not update_dict:
        return 0
    
    result = await db.execute(
        select(Mapping).where(Mapping.id.in_(bulk_update.mapping_ids))
    )
    mappings = result.scalars().all()
    
    for mapping in mappings:
        for key, value in update_dict.items():
            setattr(mapping, key, value)
    
    await db.commit()
    return len(mappings)


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a mapping."""
    result = await db.execute(
        select(Mapping).where(Mapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    await db.delete(mapping)
    await db.commit()


@router.post("/project/{project_id}/export")
async def export_mappings(
    project_id: uuid.UUID,
    mappings: List[Dict[str, Any]],
    db: AsyncSession = Depends(get_db)
):
    """Export mapped data as Excel file.
    
    Accepts mappings in the hierarchical format and exports to target format.
    """
    # Get project
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get target ERP fields
    target_erp = project.target_erp
    system = erp_service.get_system(target_erp)
    target_fields = system.get("fields", []) if system else []
    
    # Build export data
    export_rows = []
    for mapping in mappings:
        if mapping.get("target_field") and mapping.get("source_field"):
            target_name = mapping.get("target_field")
            for field in target_fields:
                if field["id"] == mapping.get("target_field"):
                    target_name = field["name"]
                    break
            
            export_rows.append({
                "Source Field": mapping.get("source_field"),
                "Target Field": target_name,
                "Source Type": mapping.get("source_type", ""),
                "Target Type": mapping.get("target_type", ""),
                "Confidence": mapping.get("confidence", 0),
                "Method": mapping.get("method", "")
            })
    
    if not export_rows:
        raise HTTPException(status_code=400, detail="No valid mappings to export")
    
    df = pd.DataFrame(export_rows)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Mapped COA')
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=mapped_coa_{target_erp}.xlsx"
        }
    )
