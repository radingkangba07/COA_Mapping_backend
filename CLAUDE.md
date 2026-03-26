# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chart of Accounts (COA) Migration Platform — helps organizations migrate their COA between ERP systems (SAP, Oracle NetSuite, Microsoft Dynamics, QuickBooks, Sage, Xero). Provides fuzzy matching, hierarchical mapping, file management, and multi-tenant project workflows.

## Current State (Legacy)

Two parallel backend implementations exist in the repo. Both are being replaced by the `src/` refactor described below.

### backend/ (MongoDB monolith, previously active)
```bash
cd backend && source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
# Requires MongoDB at mongodb://localhost:27017 (see backend/.env)
```
- Single `server.py` with all routes + Pydantic models + in-memory session stores
- Services → Repositories → MongoDB (Motor async driver)
- Imports `erp_service`, `matching_service`, `storage_service` from `services/api-service/` via sys.path

### services/api-service/ (PostgreSQL, partially built)
- SQLAlchemy models, Pydantic schemas, routers — but not deployed as primary backend
- Contains the ERP definitions, fuzzy matching logic, and storage provider code that `backend/` imports

---

## Target Architecture (Refactor)

Full specification: `specs/refactoring/refactoring-specification.md` — covers architecture, DB schema, API endpoints, NATS integration, module specs, and implementation phases.
Tasks: `specs/refactoring/tasks.md` — 92 tasks across 9 phases.
Worktree config: `specs/refactoring/worktree.config.sh` — multi-agent orchestration config.

### Stack
FastAPI, PostgreSQL (asyncpg), Alembic, Pydantic v2, NATS JetStream, boto3 (S3-compatible)

### Layout
```
src/
├── main.py                    # FastAPI app, lifespan, routers
├── core/                      # Shared infrastructure
│   ├── config.py              # pydantic-settings
│   ├── database.py            # async SQLAlchemy + get_db
│   ├── security.py            # JWT + bcrypt
│   ├── exceptions.py          # Domain exceptions → HTTP
│   ├── base_repository.py     # Generic CRUD
│   ├── nats_client.py         # JetStream lifecycle
│   └── s3_client.py           # boto3 lifecycle
├── modules/
│   ├── auth/                  # JWT auth (register, login, refresh)
│   ├── projects/              # Companies, projects, access control, dashboard
│   ├── mappings/              # Account mappings, fuzzy matching (RapidFuzz)
│   ├── storage/               # File upload/download via S3
│   ├── jobs/                  # Async job queue via NATS JetStream
│   └── erp/                   # ERP definitions from YAML config
├── config/
│   ├── erp_systems.yaml
│   └── account_type_mappings.yaml
└── migrations/                # Alembic
```

### Module pattern
Each module: `models.py` → `schemas.py` → `protocols.py` (typing.Protocol) → `repository.py` → `service.py` → `routes.py` → `dependencies.py` (FastAPI Depends wiring)

### Commands (refactored project)
```bash
# Install (uses uv for fast dependency management)
uv sync --dev                     # install all deps + dev deps, creates venv automatically
uv lock                           # regenerate uv.lock after changing pyproject.toml

# Migrations
uv run alembic upgrade head                              # apply all
uv run alembic revision --autogenerate -m "description"  # generate new

# Run server
uv run uvicorn src.main:app --reload --port 8001

# Tests
uv run pytest src/tests/ -v                    # all
uv run pytest src/tests/test_auth/ -v          # single module
uv run pytest src/tests/test_auth/test_service.py::test_login -v  # single test

# Lint & type check (same checks as CI)
uv run ruff check src/                   # catches undefined names, unused imports, bad syntax, security issues
uv run ruff format src/ --check          # format check (or without --check to auto-fix)
uv run mypy src/ --ignore-missing-imports  # static type checking — catches type errors without running code

# Add a dependency
uv add fastapi                    # production dep
uv add --dev pytest               # dev-only dep

# Docker (local dev: postgres + nats + minio)
docker-compose -f src/docker-compose.yml up -d
```

### Strict rules — read before writing any code

1. **Search before creating.** Before writing any new file, function, constant, type, utility, or helper — search the codebase (`src/`, `src/core/`, other modules) for existing code that does the same thing. Reuse it. If it almost fits, extend it rather than duplicating.
2. **No speculative abstractions.** Do not create constants files, utility modules, base classes, or shared helpers unless a task explicitly requires it or the same logic already exists in 3+ places. Three similar lines are better than a premature abstraction.
3. **Only what the task asks for.** Implement exactly what the task description says. Do not add "nice to have" extras — no bonus constants, no convenience wrappers, no extra validation layers, no new files beyond what the task specifies.
4. **One source of truth.** Enum values, permission levels, status strings, ERP IDs — these must be defined in exactly one place. If a definition already exists in a model, schema, or config, import it. Never redefine it as a separate constant.
5. **Minimal footprint.** Prefer inline values over indirection. `status="draft"` in a function body is fine — you don't need a `STATUS_DRAFT = "draft"` constant unless it's used across multiple modules.

### Key design decisions
- **DI via FastAPI Depends()** with Protocol interfaces — services never touch DB directly
- **Permission model**: 4-tier hierarchy (viewer=1, editor=2, approver=3, admin=4) enforced at service layer
- **ERP config in YAML** — adding an ERP requires zero code changes
- **NATS graceful degradation** — if NATS unavailable, jobs run synchronously in-process
- **Mapping bulk save is destructive** — DELETE + INSERT in a single transaction
- **Soft delete for files** — `is_deleted` flag in DB, hard delete from S3
- **No parsed_data in DB** — large parsed file content stored as S3 artifact, not in PostgreSQL

### CI (GitHub Actions)

`.github/workflows/ci.yml` runs on every PR to `main` or `feat/**` branches:

| Job | What it catches | Needs DB? |
|-----|----------------|-----------|
| **Lint (ruff)** | Undefined names, unused imports, bad syntax, security issues, import ordering, print statements | No |
| **Type check (mypy)** | Type mismatches, wrong return types, missing attributes, None safety | No |
| **Tests (pytest)** | Logic errors, integration failures, regressions | Yes (PostgreSQL service container) |
| **Migration check** | Model changes not captured in Alembic migrations | Yes |

Tool configs in `pyproject.toml` under `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`.
