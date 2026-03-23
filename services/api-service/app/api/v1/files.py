"""File upload and management endpoints."""
import io
import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.core.database import get_db
from app.models.project import Project
from app.models.file import File as FileModel, FileType
from app.schemas.file import FileResponse, FileUploadResponse

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    source_erp: str = Form(default="unknown"),
    target_erp: str = Form(default="unknown"),
    project_id: str = Form(default=None),
    file_type: str = Form(default="source_coa"),
    db: AsyncSession = Depends(get_db)
):
    """Upload an Excel/CSV file and parse its contents.
    
    If project_id is not provided, a new project is created.
    Returns parsed data for the frontend to use.
    """
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(
            status_code=400,
            detail="Only Excel (.xlsx, .xls) and CSV files are supported"
        )
    
    try:
        contents = await file.read()
        
        # Parse file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Create or get project
        if project_id:
            try:
                proj_uuid = uuid.UUID(project_id)
                result = await db.execute(
                    select(Project).where(Project.id == proj_uuid)
                )
                project = result.scalar_one_or_none()
                if not project:
                    raise HTTPException(status_code=404, detail="Project not found")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid project ID format")
        else:
            # Create new project
            project = Project(
                name=f"Migration - {file.filename}",
                source_erp=source_erp,
                target_erp=target_erp
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)
        
        # Store file record
        file_record = FileModel(
            project_id=project.id,
            file_type=file_type,
            original_filename=file.filename,
            columns={"columns": df.columns.tolist()},
            row_count=len(df),
            parsed_data={"data": df.fillna("").to_dict(orient='records')}
        )
        db.add(file_record)
        await db.commit()
        await db.refresh(file_record)
        
        # Return parsed data
        all_data = df.fillna("").to_dict(orient='records')
        
        return FileUploadResponse(
            file_id=file_record.id,
            session_id=str(project.id),
            file_name=file.filename,
            columns=df.columns.tolist(),
            row_count=len(df),
            sample_data=all_data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.get("/project/{project_id}", response_model=List[FileResponse])
async def get_project_files(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all files for a project."""
    result = await db.execute(
        select(FileModel)
        .where(FileModel.project_id == project_id)
        .order_by(FileModel.created_at.desc())
    )
    files = result.scalars().all()
    return [FileResponse.model_validate(f) for f in files]


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific file by ID."""
    result = await db.execute(
        select(FileModel).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse.model_validate(file)


@router.get("/{file_id}/data")
async def get_file_data(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get parsed data for a file."""
    result = await db.execute(
        select(FileModel).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "file_id": str(file.id),
        "filename": file.original_filename,
        "columns": file.columns.get("columns", []) if file.columns else [],
        "row_count": file.row_count,
        "data": file.parsed_data.get("data", []) if file.parsed_data else []
    }


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete a file."""
    result = await db.execute(
        select(FileModel).where(FileModel.id == file_id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    await db.delete(file)
    await db.commit()
