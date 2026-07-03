import io
import logging

import pandas as pd
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.exceptions import NotFoundError
from src.modules.erp.dependencies import get_erp_service
from src.modules.erp.schemas import (
    AccountTypesResponse,
    ConnectionMethod,
    ERPSystem,
    ERPVendor,
    SampleDataResponse,
)
from src.modules.erp.service import ERPConfigService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/erp-systems", tags=["erp"])
legacy_erp_router = APIRouter(prefix="/api/v1", tags=["erp"], include_in_schema=False)


# ── Vendor endpoints (must be declared before /{erp_id}) ─────────────────────


@router.get("/vendors", response_model=list[ERPVendor])
async def list_vendors(service: ERPConfigService = Depends(get_erp_service)):
    try:
        return [ERPVendor(**v) for v in service.get_vendors()]
    except Exception:
        logger.exception("Failed to list ERP vendors")
        return JSONResponse(status_code=500, content={"detail": "Failed to load vendors"})


@router.get("/vendors/{vendor_id}/products", response_model=list[ERPSystem])
async def list_vendor_products(vendor_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        products = service.get_products_for_vendor(vendor_id)
        return [
            ERPSystem(id=p["id"], name=p["name"], **{k: v for k, v in p.items() if k not in ("id", "name")})
            for p in products
        ]
    except Exception:
        logger.exception("Failed to list products for vendor '%s'", vendor_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load vendor products"})


# ── Connection methods (static list) ─────────────────────────────────────────


@router.get("/connection-methods", response_model=list[ConnectionMethod])
async def list_connection_methods(service: ERPConfigService = Depends(get_erp_service)):
    try:
        return [ConnectionMethod(**m) for m in service.get_all_connection_methods()]
    except Exception:
        logger.exception("Failed to list connection methods")
        return JSONResponse(status_code=500, content={"detail": "Failed to load connection methods"})


# ── ERP product endpoints ─────────────────────────────────────────────────────


@router.get("", response_model=list[ERPSystem])
async def list_erp_systems(service: ERPConfigService = Depends(get_erp_service)):
    try:
        systems = service.get_all_systems()
        return [
            ERPSystem(id=s["id"], name=s["name"], description=s.get("description", ""), fields=s.get("fields", []))
            for s in systems
        ]
    except Exception:
        logger.exception("Failed to list ERP systems")
        return JSONResponse(status_code=500, content={"detail": "Failed to load ERP systems"})


@router.get("/{erp_id}", response_model=ERPSystem)
async def get_erp_system(erp_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        system = service.get_system(erp_id)
        if not system:
            raise NotFoundError(f"ERP system '{erp_id}' not found")
        return ERPSystem(
            id=system["id"],
            name=system["name"],
            description=system.get("description", ""),
            vendor_id=system.get("vendor_id"),
            vendor_name=system.get("vendor_name"),
            connection_methods=system.get("connection_methods", []),
            fields=system.get("fields", []),
        )
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to get ERP system '%s'", erp_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load ERP system"})


@router.get("/{erp_id}/connection-methods", response_model=list[ConnectionMethod])
async def get_erp_connection_methods(erp_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        return [ConnectionMethod(**m) for m in service.get_connection_methods_for_erp(erp_id)]
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to get connection methods for '%s'", erp_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load connection methods"})


@router.get("/{erp_id}/account-types", response_model=AccountTypesResponse)
async def get_account_types(erp_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        system = service.get_system(erp_id)
        if not system:
            raise NotFoundError(f"ERP system '{erp_id}' not found")
        return AccountTypesResponse(erp_id=erp_id, account_types=service.get_account_types(erp_id))
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to get account types for '%s'", erp_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load account types"})


@router.get("/sample-data/{erp_id}", response_model=SampleDataResponse)
@router.get("/{erp_id}/sample-data", response_model=SampleDataResponse, include_in_schema=False)
async def get_sample_data(erp_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        system = service.get_system(erp_id)
        if not system:
            raise NotFoundError(f"ERP system '{erp_id}' not found")
        data = service.get_sample_data(erp_id)
        return SampleDataResponse(erp_id=erp_id, erp_name=system["name"], data=data, row_count=len(data))
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to get sample data for '%s'", erp_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to load sample data"})


@router.get("/sample-data/{erp_id}/download")
@router.get("/{erp_id}/sample-data/download", include_in_schema=False)
async def download_sample_data(erp_id: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        system = service.get_system(erp_id)
        if not system:
            raise NotFoundError(f"ERP system '{erp_id}' not found")
        data = service.get_sample_data(erp_id)
        if not data:
            raise NotFoundError(f"No sample data for '{erp_id}'")
        df = pd.DataFrame(data)
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={erp_id}_sample_coa.xlsx"},
        )
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to download sample data for '%s'", erp_id)
        return JSONResponse(status_code=500, content={"detail": "Failed to generate sample data download"})


# TODO: Remove legacy alias routes once frontend is updated to use /api/v1/erp-systems/* paths


@legacy_erp_router.get("/")
async def legacy_root():
    return {"message": "COA Migration System API", "version": "3.0.0", "architecture": "postgresql-modular"}


@legacy_erp_router.get("/account-types/{target_system}")
async def legacy_account_types(target_system: str, service: ERPConfigService = Depends(get_erp_service)):
    try:
        system = service.get_system(target_system)
        if not system:
            raise NotFoundError(f"Target ERP '{target_system}' not found")
        return {"account_types": service.get_account_types(target_system)}
    except NotFoundError:
        raise
    except Exception:
        logger.exception("Failed to get account types for '%s'", target_system)
        return JSONResponse(status_code=500, content={"detail": "Failed to load account types"})
