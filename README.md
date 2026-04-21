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

`.env.example` is the full list of vars the app reads — copy it, then at minimum update:

- `DATABASE_URL` — your Postgres URL
- `JWT_SECRET` — set a random string (the default is `change-me-...`)

Everything else (NATS, S3/MinIO, CORS, `APP_URL`) ships with working local-dev defaults.

**Magic-link login needs Resend.** The auth flow at `POST /api/v1/auth/login` emails a sign-in link via [Resend](https://resend.com). Without `RESEND_API_KEY` set, the endpoint returns success but no email is sent. Add to `.env` if you want to actually log in:

```
RESEND_API_KEY=re_xxx
RESEND_FROM_EMAIL=noreply@yourdomain.com
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

All SQLAlchemy models and Alembic migrations live in the **coa-db-models** package, installed as a git dependency from its `develop` branch. Every `uv sync` in CI and Docker passes `--upgrade-package coa-db-models`, so the latest upstream commit is pulled automatically on each install — no lock bump required.

For local development, run `uv sync --dev --upgrade-package coa-db-models` when you want to pick up a new upstream change. (Plain `uv sync --dev` will use the locally-pinned SHA, which is fine for offline work.)

### If you need a schema change

Make it in `coa-db-models`, not here. Add the model there, generate the migration there, then push to `develop` — your next `uv sync --upgrade-package coa-db-models` (or the next CI run) will pull it in.

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

## Logging

All logs go through [structlog](https://www.structlog.org/). Output format is gated on `APP_ENV`:

| `APP_ENV` | Output format |
|-----------|---------------|
| `production` | JSON, one event per line (ready for log aggregators) |
| anything else (default `development`) | Colored console, human-readable |

Existing `logger = logging.getLogger(__name__)` call sites are bridged through the same pipeline, so every module log (auth, jobs, mappings, storage, NATS consumer, …) renders in the same format without code changes.

### HTTP request audit log

An audit middleware emits one structured event per request. Health checks, `OPTIONS` preflight, and docs paths are excluded.

Fields:

| Field | Source | Notes |
|-------|--------|-------|
| `ts` | ISO-8601 UTC (structlog `TimeStamper`) | |
| `event` | `"http_request"` | |
| `user_id` | JWT `sub` claim | `null` if no Bearer token or token invalid. No DB call |
| `method` | `request.method` | |
| `path` | `request.url.path` | Query string omitted to avoid logging sensitive params |
| `status` | `response.status_code` | |
| `duration_ms` | Integer milliseconds | |
| `ip` | `X-Forwarded-For` first hop, else `request.client.host` | |
| `user_agent` | `User-Agent` header | |

Secrets, tokens, email addresses, and request/response bodies are never logged.

### Sample JSON line (production)

```json
{"event":"http_request","ts":"2026-04-19T12:00:00Z","level":"info","logger":"audit","user_id":"…","method":"GET","path":"/api/v1/projects","status":200,"duration_ms":42,"ip":"10.0.0.1","user_agent":"curl/8.4.0"}
```

### Sample dev output

```
[info     ] http_request                 [audit] method=GET path=/api/v1/projects status=200 duration_ms=42 …
```

### Log aggregation (Loki + Grafana)

Local observability stack ships with the compose file. Start it with:

```bash
docker compose -f src/docker-compose.yml up -d loki promtail grafana
```

Grafana is at http://localhost:3000 (default `admin` / `admin`). See [docs/observability-dev.md](docs/observability-dev.md) for the end-to-end local workflow, including how to run the API in production log mode so Promtail can parse the JSON. Production deployment paths (self-hosted vs Grafana Cloud free tier) are in [docs/observability-production.md](docs/observability-production.md).

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

Full OpenAPI at http://localhost:8001/api/docs. Summary of what's mounted:

| Module | Prefix | Endpoints | Auth |
|--------|--------|-----------|------|
| Auth | `/api/v1/auth` | `POST /register`, `GET /verify`, `POST /login` (sends magic-link email), `GET /magic-link` (consumes token), `POST /refresh`, `POST /logout`, `GET /me`, `GET /invite` | `/me`, `/logout`, `/refresh` require Bearer. Others are public. |
| Users | `/api/v1/users` | `GET /me/orgs` | Yes |
| Orgs | `/api/v1/orgs` | `POST /{id}/invitations`, `GET /{id}/invitations`, `DELETE /{id}/invitations/{inv_id}`, `GET /{id}/members`, `DELETE /{id}/members/{user_id}` | Yes |
| Projects | `/api/v1` | `POST/GET /projects`, `GET/PATCH/DELETE /projects/{id}`, `POST/GET /projects/{id}/access`, `DELETE /projects/{id}/access/{user_id}`, `GET /dashboard/projects/{id}` | Yes |
| Mappings | `/api/v1/mappings` | `POST/GET /project/{id}`, `GET /project/{id}/stats`, `POST /project/{id}/export`, `PATCH/DELETE /{mapping_id}`, `POST /bulk-update`, `PATCH /bulk-status`, `POST /hierarchical`, `POST /fuzzy-match` | Yes |
| Account-Type Mappings | `/api/v1/mappings` | `POST/GET/DELETE /project/{id}/account-type-mappings`, `PATCH /account-type-mappings/{id}` | Yes |
| Mapping Suggestions | `/api/v1/mappings` | `GET /project/{id}/suggestions` | Yes |
| ERP | `/api/v1/erp-systems` | `GET ""`, `GET /{erp_id}`, `GET /{erp_id}/account-types`, `GET /sample-data/{erp_id}`, `GET /sample-data/{erp_id}/download` | No |
| Storage | `/api/v1/storage` | `POST /upload`, `GET /files/{id}`, `DELETE /files/{id}`, `GET /download/{id}`, `GET /signed-url/{id}`, `GET /project/{id}/files` | Yes |
| Files (alias) | `/api/v1/files` | Same surface as `/api/v1/storage/files/...` — legacy path kept for the mobile client | Yes |
| Jobs | `/api/v1/jobs` | `POST ""`, `GET /{id}`, `GET /{id}/status`, `GET /{id}/result`, `DELETE /{id}`, `GET /project/{id}` | Yes |
| WebSocket | `/api/v1/ws` | `/jobs/project/{id}?token=<jwt>` | Yes (JWT via query) |
| Health | — | `GET /api/v1/health` and `GET /health` | No |

## Real-time updates via WebSocket

Project-scoped WebSocket for live job status.

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

The ML worker writes terminal status to the DB and publishes just `{job_id}` on `jobs.mapping.status`. The API consumer reads the authoritative row back from the DB and broadcasts a minimal payload to every client subscribed to that project:

```json
{
  "job_id": "uuid",
  "status": "queued | running | completed | failed"
}
```

On `status == "failed"` the payload also includes an `error_message` string:

```json
{
  "job_id": "uuid",
  "status": "failed",
  "error_message": "..."
}
```

Full job metadata (files, timestamps, source/target systems) is NOT broadcast — fetch it via `GET /api/v1/jobs/{job_id}` when a status change arrives.