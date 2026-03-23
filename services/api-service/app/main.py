"""Main FastAPI application for COA Migration API Service."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.v1 import (
    erp_router,
    projects_router,
    files_router,
    jobs_router,
    mappings_router
)
from app.api.legacy import legacy_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting COA Migration API Service...")
    await init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="COA Migration System API - Microservices Architecture",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.CORS_ORIGINS.split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 router with /api/v1 prefix
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(erp_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(files_router)
api_v1_router.include_router(jobs_router)
api_v1_router.include_router(mappings_router)

# Include routers
app.include_router(api_v1_router)

# Legacy API router at /api for backward compatibility with existing frontend
app.include_router(legacy_router, prefix="/api", tags=["Legacy"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "COA Migration API",
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "api-service",
        "version": settings.APP_VERSION
    }
