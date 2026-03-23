"""API v1 routes."""
from app.api.v1.erp import router as erp_router
from app.api.v1.projects import router as projects_router
from app.api.v1.files import router as files_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.mappings import router as mappings_router

__all__ = [
    "erp_router",
    "projects_router",
    "files_router",
    "jobs_router",
    "mappings_router"
]
