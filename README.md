# COA Migration API

Backend for the Chart of Accounts Migration Platform — helps organizations migrate their COA between ERP systems (SAP, Oracle NetSuite, Microsoft Dynamics, QuickBooks, Sage, Xero).

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- PostgreSQL 15+ (with pgvector extension)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (required for NATS)

## Quick Start

### 1. Clone the repo

```bash
git clone <repo-url>
cd COA_Mapping_backend_V0
```

### 2. Install dependencies

```bash
uv sync --dev
```

### 3. Set up PostgreSQL

```bash
psql -U your_username -d postgres -c "CREATE DATABASE coa_migration"
psql -U your_username -d coa_migration -c "CREATE EXTENSION IF NOT EXISTS vector"
```

### 4. Configure environment

```bash
cp .env.example .env
```

Update `.env` with your credentials:

```
DATABASE_URL=postgresql+asyncpg://your_username@localhost:5432/coa_migration
APP_URL=http://localhost:8001
```

### 5. Run database migrations

Migrations are managed in the [coa-db-models](https://github.com/bhavna-linkedrp/coa-db-models.) repo. Clone it and run:

```bash
cd ../coa-db-models
uv run alembic upgrade head
```

### 6. Start NATS

```bash
docker compose -f src/docker-compose.yml up -d nats
```

### 7. Run the server

```bash
uv run uvicorn src.main:app --reload --port 8001
```

API docs available at http://localhost:8001/api/docs

## Shared Models & Migrations

All SQLAlchemy models and Alembic migrations live in the **coa-db-models** package, installed as a git dependency. This repo only contains application logic (schemas, services, routes).

### When `coa-db-models` is updated

If someone pushes changes to `coa-db-models` (new model, new column, new migration), you need to update your local install:

```bash
uv lock --upgrade-package coa-db-models   # fetches the latest commit
uv sync --dev                              # installs it
```

Then commit the updated `uv.lock` so other developers get the change too.

### If you need a schema change

Make it in `coa-db-models`, not here. Add the model there, generate the migration there, then update this repo's dependency with the commands above.

## Running Tests

```bash
# Create test database (once)
psql -U your_username -d postgres -c "CREATE DATABASE coa_migration_test"
psql -U your_username -d coa_migration_test -c "CREATE EXTENSION IF NOT EXISTS vector"

# Run all tests
TEST_DATABASE_URL="postgresql+asyncpg://your_username@localhost:5432/coa_migration_test" uv run pytest src/tests/ -v

# Run a single module
uv run pytest src/tests/test_auth/ -v
```

## Linting

```bash
uv run ruff check src/
uv run ruff format src/ --check
```

## Required Services

### NATS (async job queue)

The server will not start without a running NATS instance:

```bash
docker compose -f src/docker-compose.yml up -d nats
```

## Optional Services

### MinIO (S3-compatible file storage)

Without MinIO, file upload/download won't work but all other features do.

```bash
docker compose -f src/docker-compose.yml up -d minio minio-init
```

## API Endpoints

| Module | Endpoints | Auth Required |
|--------|-----------|---------------|
| Auth | `/api/v1/auth/register`, `/login`, `/verify`, `/magic-link`, `/refresh`, `/logout`, `/me` | No (except `/me`) |
| Orgs | `/api/v1/orgs/{id}/invitations`, `/members`, `/users/me/orgs` | Yes |
| Projects | `/api/v1/projects`, `/companies`, `/dashboard` | Yes |
| Mappings | `/api/v1/mappings/project/{id}`, `/fuzzy-match`, `/hierarchical` | Yes |
| Account Type Mappings | `/api/v1/mappings/project/{id}/account-type-mappings` | Yes |
| Mapping Suggestions | `/api/v1/mappings/project/{id}/suggestions` | Yes |
| ERP | `/api/v1/erp-systems`, `/sample-data/{id}` | No |
| Storage | `/api/v1/storage/upload`, `/download/{id}`, `/project/{id}/files` | Yes |
| Jobs | `/api/v1/jobs` | Yes |
| WebSocket | `/api/v1/ws/jobs/project/{id}?token=<jwt>` | Yes (JWT via query) |
| Health | `GET /api/v1/health` | No |

## Real-time updates via WebSocket

Project-scoped WebSocket for live job status`.

### Endpoint

```
ws://localhost:8001/api/v1/ws/jobs/project/{project_id}?token=<jwt>
```

JWT is passed as a query param because browsers can't set headers on `WebSocket`. Close codes:

| Code | Meaning |
|------|---------|
| 4401 | No token / invalid / expired |
| 4403 | Valid token, no access to project |
| 1000 | Normal close |
| 1006 | Network drop — reconnect |

### Message format (server → client)

Server broadcasts the **raw NATS status message** (`jobs.mapping.status`) from the ML worker, unchanged:

```json
{
  "job_id": "uuid",
  "project_id": "uuid | null",
  "company_id": "string | null",
  "job_type": "mapping",
  "status": "queued | running | completed | failed",
  "source_file_id": "uuid | null",
  "target_file_id": "uuid | null",
  "mapping_file_id": "uuid | null",
  "account_type_mapping_file_id": "uuid | null",
  "triggered_by": "uuid | null",
  "created_at": "ISO-8601 | null",
  "started_at": "ISO-8601 | null",
  "completed_at": "ISO-8601 | null",
  "event_at": "ISO-8601 | null",
  "error_message": "string | null",
  "metadata": { "source_system": "string | null", "target_system": "string | null" }
}
```