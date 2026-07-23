import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.audit_middleware import audit_middleware
from src.core.config import get_settings
from src.core.database import close_db, init_db
from src.core.exceptions import AppError
from src.core.logging import setup_logging
from src.core.nats_client import close_nats, connect_nats, get_jetstream
from src.core.resend_client import close_resend, init_resend, is_resend_available
from src.core.s3_client import close_s3_client, get_s3_client, init_s3_client
from src.modules.auth.routes import orgs_router, users_router
from src.modules.auth.routes import router as auth_router
from src.modules.erp.routes import legacy_erp_router
from src.modules.erp.routes import router as erp_router
from src.modules.jobs.routes import router as jobs_router
from src.modules.mappings.account_types.routes import router as account_types_router
from src.modules.mappings.routes import legacy_mappings_router
from src.modules.mappings.routes import router as mappings_router
from src.modules.mappings.suggestions.routes import router as suggestions_router
from src.modules.projects.routes import router as projects_router
from src.modules.storage.routes import files_router
from src.modules.storage.routes import router as storage_router
from src.modules.websocket.routes import router as websocket_router
from src.modules.workstreams.routes import router as workstreams_router
from src.modules.item_profile.router import router as item_profile_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    settings = get_settings()
    logger.info("Starting COA Migration API (env=%s)", settings.app_env)
    await init_db()
    await connect_nats(settings.nats_url, settings.nats_stream_name)
    init_s3_client()

    # NATS is required — connect_nats raises if it can't connect, so jetstream is guaranteed here.
    from src.core import database
    from src.modules.jobs.consumer import NATSConsumer
    from src.modules.jobs.repository import JobRepository

    assert database._async_session_factory is not None, "init_db() must run before NATS consumer start"
    session = database._async_session_factory()
    from src.modules.websocket.connection_manager import ConnectionManager

    app.state.connection_manager = ConnectionManager()

    consumer = NATSConsumer(
        get_jetstream(),
        JobRepository(session),
        session=session,
        connection_manager=app.state.connection_manager,
    )
    await consumer.start()
    logger.info("NATS consumer started")

    init_resend()
    yield
    logger.info("Shutting down COA Migration API")
    close_resend()
    await consumer.stop()
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
app.middleware("http")(audit_middleware)


# Global exception handler for domain errors
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("%s %s -> %d: %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(orgs_router)
app.include_router(projects_router)
app.include_router(workstreams_router)
app.include_router(mappings_router)
app.include_router(account_types_router)
app.include_router(suggestions_router)
app.include_router(erp_router)
app.include_router(storage_router)
app.include_router(files_router)
app.include_router(jobs_router)
app.include_router(websocket_router)
app.include_router(legacy_erp_router)
app.include_router(legacy_mappings_router)
app.include_router(item_profile_router)


# Health check — registered at both the prefixed API path and an unprefixed
# `/health` so container healthchecks work regardless of root_path mounting.
@app.get("/health", include_in_schema=False)
@app.get("/api/v1/health")
async def health_check() -> dict:
    status_val = "healthy"

    # NATS is required at startup — if the app is up, NATS is connected.
    nats_status = "connected"

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

    email_status = "available" if is_resend_available() else "disabled"

    return {
        "status": status_val,
        "service": "coa-migration-api",
        "version": "3.0.0",
        "database": db_status,
        "nats": nats_status,
        "storage": storage_status,
        "email": email_status,
    }
