import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.database import close_db, init_db
from src.core.exceptions import AppError
from src.core.logging import setup_logging
from src.core.nats_client import close_nats, connect_nats, is_nats_available
from src.core.s3_client import close_s3_client, get_s3_client, init_s3_client
from src.modules.auth.routes import router as auth_router
from src.modules.erp.routes import legacy_erp_router
from src.modules.erp.routes import router as erp_router
from src.modules.jobs.routes import router as jobs_router
from src.modules.mappings.routes import legacy_mappings_router
from src.modules.mappings.routes import router as mappings_router
from src.modules.projects.routes import router as projects_router
from src.modules.storage.routes import files_router
from src.modules.storage.routes import router as storage_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    settings = get_settings()
    logger.info("Starting COA Migration API (env=%s)", settings.app_env)
    await init_db()
    await connect_nats(settings.nats_url, settings.nats_stream_name)
    init_s3_client()
    yield
    logger.info("Shutting down COA Migration API")
    await close_nats()
    close_s3_client()
    await close_db()


app = FastAPI(
    title="COA Migration API",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler for domain errors
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("%s %s -> %d: %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(mappings_router)
app.include_router(erp_router)
app.include_router(storage_router)
app.include_router(files_router)
app.include_router(jobs_router)
app.include_router(legacy_erp_router)
app.include_router(legacy_mappings_router)


# Health check
@app.get("/api/v1/health")
async def health_check() -> dict:
    status_val = "healthy"

    # Check NATS
    nats_status = "connected" if is_nats_available() else "disabled"

    # Check S3
    s3_client = get_s3_client()
    storage_status = "available" if s3_client else "unavailable"

    # Check DB
    db_status = "connected"
    try:
        from sqlalchemy import text as sa_text

        from src.core.database import _engine

        if _engine:
            async with _engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
        else:
            db_status = "disconnected"
            status_val = "degraded"
    except Exception:
        db_status = "disconnected"
        status_val = "degraded"

    return {
        "status": status_val,
        "service": "coa-migration-api",
        "version": "3.0.0",
        "database": db_status,
        "nats": nats_status,
        "storage": storage_status,
    }
