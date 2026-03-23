# COA Migration API Service

## Overview

This is the refactored API service for the COA Migration System, implementing a microservices architecture with:

- **FastAPI** for REST API
- **PostgreSQL** for persistent storage
- **RabbitMQ** for async job queue (integration ready)
- **SQLAlchemy** with async support

## Directory Structure

```
api-service/
├── app/
│   ├── api/
│   │   ├── v1/          # New v1 API endpoints
│   │   └── legacy.py    # Backward-compatible endpoints
│   ├── core/
│   │   ├── config.py    # Settings management
│   │   └── database.py  # Database connection
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   └── services/        # Business logic
├── migrations/          # Alembic migrations
└── tests/
```

## API Endpoints

### Legacy API (Backward Compatible)
- `GET /api/` - Root
- `GET /api/erp-systems` - List ERP systems
- `POST /api/upload` - Upload COA file
- `POST /api/hierarchical-mapping` - Create mapping
- `POST /api/export` - Export mapped data

### New v1 API (Async Job Flow)
- `POST /api/v1/projects` - Create project
- `POST /api/v1/files/upload` - Upload file
- `POST /api/v1/jobs` - Create async job
- `GET /api/v1/jobs/{id}/status` - Poll job status
- `GET /api/v1/mappings/project/{id}` - Get mappings

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Message Queue Contract

See `app/services/queue_service.py` for the message schema used for ML service integration.
