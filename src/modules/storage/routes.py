import io
import logging
import uuid as uuid_mod
from uuid import UUID

import pandas as pd
from coa_db_models.auth.models import User
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.exceptions import AppError
from src.modules.auth.dependencies import get_current_user
from src.modules.item_profile.dependencies import get_item_profile_service
from src.modules.item_profile.service import ItemProfileService
from src.modules.projects.dependencies import require_project_access
from src.modules.storage.dependencies import get_storage_service
from src.modules.storage.schemas import FileListResponse, FileResponse, FileUploadResponse, SignedUrlResponse
from src.modules.storage.service import StorageService

_ITEM_PROFILE_FILE_TYPES = frozenset(["item_source", "items", "source_erp"])

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])
files_router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    project_id: UUID = Form(...),
    file_type: str = Form("source_erp"),
    job_id: UUID | None = Form(None),
    workstream_id: UUID | None = Form(None),
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        data = await file.read()
        result = await service.upload_file(
            file_data=data,
            filename=file.filename or "unknown",
            project_id=project_id,
            file_type=file_type,
            user_id=user.id,
            uploaded_by=user.id,
            job_id=job_id,
            workstream_id=workstream_id,
        )
        return {"success": True, "file": FileUploadResponse.model_validate(result)}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to upload file to project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to upload file"})


@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        return await service.get_file(file_id, user.id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get file"})


@router.get("/download/{file_id}")
async def download_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        data, content_type, filename = await service.download_file(file_id, user.id)
        return StreamingResponse(
            io.BytesIO(data),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to download file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to download file"})


@router.get("/signed-url/{file_id}", response_model=SignedUrlResponse)
async def get_signed_url(
    file_id: UUID,
    expires_in: int = Query(3600, ge=60, le=86400),
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        url = await service.get_signed_url(file_id, user.id, expires_in)
        return SignedUrlResponse(
            file_id=file_id,
            signed_url=url,
            expires_in=expires_in if url else None,
            supported=url is not None,
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get signed URL for file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get signed URL"})


@router.get("/project/{project_id}/files", response_model=FileListResponse)
async def list_project_files(
    project_id: UUID,
    file_type: str | None = Query(None),
    _access=Depends(require_project_access("viewer")),
    service: StorageService = Depends(get_storage_service),
):
    try:
        files = await service.list_files(project_id, file_type)
        return FileListResponse(
            project_id=project_id,
            files=[FileResponse.model_validate(f) for f in files],
            total=len(files),
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list files for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list files"})


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        await service.delete_file(file_id, user.id)
        return {"success": True, "message": "File deleted"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to delete file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to delete file"})


@files_router.post("/upload")
async def files_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Query(...),
    file_type: str = Query(...),
    source_system: str = Query(default="unknown"),
    target_system: str = Query(default="unknown"),
    workstream_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
    profile_service: ItemProfileService = Depends(get_item_profile_service),
):
    """Upload a file, persist to storage, parse contents — matches legacy response."""
    try:
        contents = await file.read()
        filename = file.filename or "unknown"

        # Parse file into DataFrame for sample_data
        df = None
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(contents))
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(contents))
        if df is not None:
            df.columns = df.columns.str.strip()

        # Create session_id for legacy compatibility
        session_id = str(uuid_mod.uuid4())

        pid = UUID(project_id)

        # Persist file via storage service
        result = await service.upload_file(
            file_data=contents,
            filename=filename,
            project_id=pid,
            file_type=file_type,
            user_id=user.id,
            uploaded_by=user.id,
            workstream_id=workstream_id,
        )

        # Auto-kickoff item profile run for item source files
        profile_run_id = None
        if file_type in _ITEM_PROFILE_FILE_TYPES:
            try:
                s3_key = result.storage_path
                run_result = await profile_service.initiate_run(pid, s3_key, user)
                profile_run_id = str(run_result["run_id"])
                background_tasks.add_task(
                    profile_service.process_run,
                    run_result["run_id"],
                    pid,
                    s3_key,
                )
                logger.info("Auto-kicked item profile run %s for project %s", profile_run_id, project_id)
            except Exception:
                logger.exception("Failed to auto-kick item profile run for project %s", project_id)

        all_data = df.fillna("").to_dict(orient="records") if df is not None else []

        return {
            "session_id": session_id,
            "file_name": filename,
            "columns": df.columns.tolist() if df is not None else [],
            "row_count": len(df) if df is not None else 0,
            "sample_data": all_data,
            "file": FileUploadResponse.model_validate(result),
            "profile_run_id": profile_run_id,
        }
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to upload file (legacy) for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to upload file"})


@files_router.get("/{file_id}", response_model=FileResponse)
async def files_get(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        return await service.get_file(file_id, user.id)
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get file"})


@files_router.get("/{file_id}/data")
async def files_get_data(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    """Download, parse, and return file row data — matches legacy response."""
    try:
        data, _content_type, filename = await service.download_file(file_id, user.id)

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(data))
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(data))
        else:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Unsupported file format")

        df.columns = df.columns.str.strip()
        rows = df.fillna("").to_dict(orient="records")

        return {
            "file_id": str(file_id),
            "file_name": filename,
            "columns": df.columns.tolist(),
            "row_count": len(df),
            "sample_data": rows,
        }
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to get file data %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to get file data"})


@files_router.get("/{file_id}/download")
async def files_download(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        data, content_type, filename = await service.download_file(file_id, user.id)
        return StreamingResponse(
            io.BytesIO(data),
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to download file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to download file"})


@files_router.get("/project/{project_id}", response_model=FileListResponse)
async def files_list_project(
    project_id: UUID,
    file_type: str | None = Query(default=None),
    _access=Depends(require_project_access("viewer")),
    service: StorageService = Depends(get_storage_service),
):
    try:
        files = await service.list_files(project_id, file_type)
        return FileListResponse(
            project_id=project_id,
            files=[FileResponse.model_validate(f) for f in files],
            total=len(files),
        )
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to list files for project %s", project_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to list files"})


@files_router.delete("/{file_id}")
async def files_delete(
    file_id: UUID,
    user: User = Depends(get_current_user),
    service: StorageService = Depends(get_storage_service),
):
    try:
        await service.delete_file(file_id, user.id)
        return {"success": True, "message": "File deleted"}
    except AppError:
        raise
    except Exception:
        logger.exception("Failed to delete file %s", file_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to delete file"})
