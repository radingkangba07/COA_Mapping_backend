# COA Migration API

Backend for the Chart of Accounts Migration Platform — helps organizations migrate their COA between ERP systems (SAP, Oracle NetSuite, Microsoft Dynamics, QuickBooks, Sage, Xero).

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- PostgreSQL 15+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (optional, for NATS and MinIO)

## Quick Start

### 1. Install dependencies

```bash
uv sync --dev
```

### 2. Set up PostgreSQL

Create the database:

```bash
psql -U your_username -d postgres -c "CREATE DATABASE coa_migration"
```

### 3. Configure environment

Copy the example and update:

```bash
cp .env.example .env
```

Update `DATABASE_URL` in `.env` with your PostgreSQL credentials:

```
DATABASE_URL=postgresql+asyncpg://your_username@localhost:5432/coa_migration
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
```

This creates all tables. To generate a new migration after model changes:

```bash
uv run alembic revision --autogenerate -m "description of change"
```

### 5. Run the server

```bash
uv run uvicorn src.main:app --reload --port 8001
```

API docs available at http://localhost:8001/docs

### 6. Seed demo data (optional)

Populates the database with sample users, companies, projects, and mappings:

```bash
uv run python -m src.seed
```

Safe to run multiple times — skips if data already exists.

## Environments

The app supports multiple environments via `APP_ENV`:

| APP_ENV | .env file loaded | Description |
|---------|------------------|-------------|
| (unset) / `development` | `.env` | Local development |
| `testing` | `.env.testing` | Test environment |
| `staging` | `.env.staging` | Staging server |
| `production` | `.env.production` | Production server |

Set the environment:

```bash
export APP_ENV=staging
uv run uvicorn src.main:app --port 8001
```

## Logging

Logging is configured automatically on startup via `src/core/logging.py`.

- **Log level**: `DEBUG` when `DEBUG=true` in `.env`, `INFO` otherwise
- **Format**: `timestamp | LEVEL | module | message`
- **Output**: stdout (suitable for Docker/cloud log aggregation)

All service operations (login, project CRUD, file upload, job creation) and errors are logged. Logs include the environment on startup:

```
2026-04-05 10:30:00 | INFO     | src.main | Starting COA Migration API (env=development)
2026-04-05 10:30:00 | INFO     | src.core.database | Database connected
2026-04-05 10:30:01 | INFO     | src.modules.auth.service | User 'admin' logged in
```

## Optional Services

These are not required to run the backend. The app works without them.

### NATS (async job queue)

Without NATS, jobs run synchronously (still works, just not async).

```bash
docker compose -f src/docker-compose.yml up -d nats
```

Then update `.env`:

```
NATS_URL=nats://localhost:4222
```

### MinIO (S3-compatible file storage)

Without MinIO, file upload/download won't work but all other features do.

```bash
docker compose -f src/docker-compose.yml up -d minio minio-init
```

Then update `.env`:

```
S3_ENDPOINT=http://localhost:9000
```

### Start all optional services at once

```bash
docker compose -f src/docker-compose.yml up -d
```

## Running Tests

```bash
# Create test database first
psql -U your_username -d postgres -c "CREATE DATABASE coa_migration_test"

# Run all tests
uv run pytest src/tests/ -v

# Run a single module
uv run pytest src/tests/test_auth/ -v
```

## Linting

```bash
uv run ruff check src/
uv run ruff format src/ --check
```

## API Endpoints

| Module | Endpoints | Auth Required |
|--------|-----------|---------------|
| Auth | `POST /api/v1/auth/login`, `/me`, `/logout` | No (login) |
| Projects | `/api/v1/projects`, `/companies`, `/dashboard` | Yes |
| Mappings | `/api/v1/mappings/fuzzy-match`, `/hierarchical`, `/project/{id}` | Yes |
| ERP | `/api/v1/erp-systems`, `/sample-data/{id}` | No |
| Storage | `/api/v1/storage/upload`, `/download/{id}`, `/project/{id}/files` | Yes |
| Jobs | `/api/v1/jobs` | Yes |
| Health | `GET /api/v1/health` | No |

## Production Deployment (DigitalOcean)

```bash
export APP_ENV=production
```

Update `.env.production` with real credentials, then:

```bash
uv run alembic upgrade head
uv run uvicorn src.main:app --port 8001
```
