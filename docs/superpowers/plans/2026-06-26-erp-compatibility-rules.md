# ERP Compatibility Rules (DAB-1 / DA08) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a database-backed `erp_compatibility_rules` table with a CRUD repository, 300 s in-memory TTL cache, and a `GET /api/v1/erp/compatibility-check` endpoint that returns compatibility between two ERP products for a given connection method.

**Architecture:** New SQLAlchemy model lives in `src/modules/erp/models.py` (uses the shared `Base` from `coa_db_models`); repository handles precedence logic (specific connection-method rule > general null-method rule > default compatible); cache lives in the existing `ERPConfigService` singleton which is already used as a per-application cache store; route injects both the singleton (for cache) and a DB session (for queries).

**Tech Stack:** FastAPI, SQLAlchemy (async), asyncpg, Pydantic v2, pytest-asyncio

## Global Constraints

- Python ≥ 3.13; async SQLAlchemy 2.x patterns only (`select()`, `scalar_one_or_none()`)
- Use `Base` imported from `coa_db_models` (via `src.core.database`) for all SQLAlchemy models
- Ruff rules enforced: no `print`, no unused imports, isort ordering
- No speculative abstractions — implement exactly what the spec requires
- All query params (`source_product_id`, `target_product_id`, `connection_method_id`) are required; missing → HTTP 422 (FastAPI default for missing Query params)
- TTL for compatibility cache: 300 s (distinct from existing 600 s ERP list cache)
- Precedence: specific connection-method rule > general null-method rule > default compatible (`is_compatible=True`, message = "No compatibility rule found — compatible by default")

---

### Task 1: SQLAlchemy Model + Alembic Migration

**Files:**
- Create: `src/modules/erp/models.py`
- Create: `src/migrations/006_erp_compatibility_rules.py`

**Interfaces:**
- Produces: `ERPCompatibilityRule` (SQLAlchemy ORM class) with columns `id`, `source_product_id`, `target_product_id`, `connection_method_id`, `is_compatible`, `incompatibility_reason`

- [ ] **Step 1: Create `src/modules/erp/models.py`**

```python
import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from coa_db_models import Base


class ERPCompatibilityRule(Base):
    __tablename__ = "erp_compatibility_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_product_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_product_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    connection_method_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_compatible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    incompatibility_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Create `src/migrations/` directory and migration file**

Create `src/migrations/006_erp_compatibility_rules.py` with Alembic-format upgrade/downgrade:

```python
"""006_erp_compatibility_rules

Adds erp_compatibility_rules table. Rules store whether a source→target ERP
pair is compatible for a given connection method. A null connection_method_id
is a general rule that applies to all methods; specific method rules take
precedence.

Revision ID: 006
Revises: 005
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_compatibility_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_product_id", sa.String(100), nullable=False),
        sa.Column("target_product_id", sa.String(100), nullable=False),
        sa.Column("connection_method_id", sa.String(100), nullable=True),
        sa.Column("is_compatible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("incompatibility_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_erp_compat_source_target",
        "erp_compatibility_rules",
        ["source_product_id", "target_product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_erp_compat_source_target", table_name="erp_compatibility_rules")
    op.drop_table("erp_compatibility_rules")
```

- [ ] **Step 3: Verify model is importable**

Run: `uv run python -c "from src.modules.erp.models import ERPCompatibilityRule; print(ERPCompatibilityRule.__tablename__)"`
Expected: `erp_compatibility_rules`

- [ ] **Step 4: Commit**

```bash
git add src/modules/erp/models.py src/migrations/006_erp_compatibility_rules.py
git commit -m "feat(erp): add ERPCompatibilityRule SQLAlchemy model and migration 006"
```

---

### Task 2: Repository — DB-Backed check_compatibility

**Files:**
- Create: `src/modules/erp/repository.py`

**Interfaces:**
- Consumes: `ERPCompatibilityRule` from `src.modules.erp.models`
- Produces: `ERPCompatibilityRepository.check_compatibility(source, target, method) -> tuple[bool, str]`

- [ ] **Step 1: Write failing test for repository**

Add to `src/tests/test_erp/test_erp_service.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.erp.models import ERPCompatibilityRule
from src.modules.erp.repository import ERPCompatibilityRepository


@pytest.mark.asyncio
async def test_compat_default_compatible(db_session: AsyncSession):
    repo = ERPCompatibilityRepository(db_session)
    ok, msg = await repo.check_compatibility("sap", "xero", "csv_file")
    assert ok is True
    assert "default" in msg.lower()


@pytest.mark.asyncio
async def test_compat_specific_rule_incompatible(db_session: AsyncSession):
    rule = ERPCompatibilityRule(
        source_product_id="sap",
        target_product_id="xero",
        connection_method_id="cloud_saas",
        is_compatible=False,
        incompatibility_reason="SAP does not support cloud SaaS to Xero migration",
    )
    db_session.add(rule)
    await db_session.commit()
    repo = ERPCompatibilityRepository(db_session)
    ok, msg = await repo.check_compatibility("sap", "xero", "cloud_saas")
    assert ok is False
    assert "SAP" in msg


@pytest.mark.asyncio
async def test_compat_specific_rule_takes_precedence_over_general(db_session: AsyncSession):
    # General rule says incompatible
    general = ERPCompatibilityRule(
        source_product_id="sap",
        target_product_id="quickbooks",
        connection_method_id=None,
        is_compatible=False,
        incompatibility_reason="Generally incompatible",
    )
    # Specific rule for csv_file says compatible
    specific = ERPCompatibilityRule(
        source_product_id="sap",
        target_product_id="quickbooks",
        connection_method_id="csv_file",
        is_compatible=True,
        incompatibility_reason=None,
    )
    db_session.add_all([general, specific])
    await db_session.commit()
    repo = ERPCompatibilityRepository(db_session)
    ok, msg = await repo.check_compatibility("sap", "quickbooks", "csv_file")
    assert ok is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/tests/test_erp/test_erp_service.py -k "compat" -v`
Expected: ImportError or AttributeError — `ERPCompatibilityRepository` does not exist yet

- [ ] **Step 3: Create `src/modules/erp/repository.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.erp.models import ERPCompatibilityRule


class ERPCompatibilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def check_compatibility(
        self,
        source_product_id: str,
        target_product_id: str,
        connection_method_id: str,
    ) -> tuple[bool, str]:
        # Specific rule (connection_method_id matches exactly) takes precedence
        result = await self._session.execute(
            select(ERPCompatibilityRule).where(
                ERPCompatibilityRule.source_product_id == source_product_id,
                ERPCompatibilityRule.target_product_id == target_product_id,
                ERPCompatibilityRule.connection_method_id == connection_method_id,
            )
        )
        rule = result.scalar_one_or_none()

        if rule is None:
            # Fall back to general rule (null connection_method_id)
            result = await self._session.execute(
                select(ERPCompatibilityRule).where(
                    ERPCompatibilityRule.source_product_id == source_product_id,
                    ERPCompatibilityRule.target_product_id == target_product_id,
                    ERPCompatibilityRule.connection_method_id.is_(None),
                )
            )
            rule = result.scalar_one_or_none()

        if rule is None:
            return True, "No compatibility rule found — compatible by default"

        message = rule.incompatibility_reason or ("Compatible" if rule.is_compatible else "Incompatible")
        return rule.is_compatible, message
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest src/tests/test_erp/test_erp_service.py -k "compat" -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/modules/erp/repository.py src/tests/test_erp/test_erp_service.py
git commit -m "feat(erp): add ERPCompatibilityRepository with precedence logic"
```

---

### Task 3: Schema + Service Cache Helpers

**Files:**
- Modify: `src/modules/erp/schemas.py`
- Modify: `src/modules/erp/service.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `CompatibilityResult(is_compatible: bool, message: str)` Pydantic schema; `ERPConfigService.get_cached_compat(key) -> CompatibilityResult | None`; `ERPConfigService.set_cached_compat(key, result) -> None`

- [ ] **Step 1: Add `CompatibilityResult` to `schemas.py`**

Append to end of `src/modules/erp/schemas.py`:

```python
class CompatibilityResult(BaseModel):
    is_compatible: bool
    message: str
```

- [ ] **Step 2: Add 300 s cache TTL constant and helpers to `service.py`**

Add `_COMPAT_CACHE_TTL = 300` constant after the existing `_CACHE_TTL = 600` line.

Add two methods at the end of `ERPConfigService`:

```python
    # ── Compatibility cache (TTL 300 s) ───────────────────────────────────────

    def get_cached_compat(self, key: str) -> "CompatibilityResult | None":
        entry = self._cache.get(key)
        if entry and time.monotonic() - entry[0] < _COMPAT_CACHE_TTL:
            from src.modules.erp.schemas import CompatibilityResult
            return entry[1]
        return None

    def set_cached_compat(self, key: str, result: "CompatibilityResult") -> None:
        self._cache[key] = (time.monotonic(), result)
```

Note: `CompatibilityResult` is imported inside the method body to avoid a circular import (schemas imports nothing from service; service would import schemas). An alternative is a top-level import — verify there is no circular dependency before promoting to top-level.

- [ ] **Step 3: Verify ruff passes**

Run: `uv run ruff check src/modules/erp/schemas.py src/modules/erp/service.py`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add src/modules/erp/schemas.py src/modules/erp/service.py
git commit -m "feat(erp): add CompatibilityResult schema and 300s compat cache helpers"
```

---

### Task 4: Route — GET /api/v1/erp/compatibility-check

**Files:**
- Modify: `src/modules/erp/routes.py`
- Modify: `src/main.py`

**Interfaces:**
- Consumes: `ERPCompatibilityRepository` from Task 2; `CompatibilityResult` from Task 3; `ERPConfigService.get_cached_compat / set_cached_compat` from Task 3
- Produces: `GET /api/v1/erp/compatibility-check?source_product_id=&target_product_id=&connection_method_id=` → `CompatibilityResult`

- [ ] **Step 1: Write failing route tests**

Add to `src/tests/test_erp/test_erp_routes.py`:

```python
@pytest.mark.asyncio
async def test_compatibility_check_default_compatible(test_client: AsyncClient):
    resp = await test_client.get(
        "/api/v1/erp/compatibility-check",
        params={"source_product_id": "sap", "target_product_id": "xero", "connection_method_id": "csv_file"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_compatible"] is True
    assert "default" in data["message"].lower()


@pytest.mark.asyncio
async def test_compatibility_check_missing_param_returns_422(test_client: AsyncClient):
    resp = await test_client.get(
        "/api/v1/erp/compatibility-check",
        params={"source_product_id": "sap", "target_product_id": "xero"},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/tests/test_erp/test_erp_routes.py -k "compatibility" -v`
Expected: FAILED — route does not exist (404)

- [ ] **Step 3: Add `compat_router` and endpoint to `routes.py`**

Add imports at top of `src/modules/erp/routes.py`:

```python
from fastapi import Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.erp.repository import ERPCompatibilityRepository
from src.modules.erp.schemas import CompatibilityResult
```

Add after existing `legacy_erp_router` declaration:

```python
compat_router = APIRouter(prefix="/api/v1/erp", tags=["erp"])


@compat_router.get("/compatibility-check", response_model=CompatibilityResult)
async def check_compatibility(
    source_product_id: str = Query(...),
    target_product_id: str = Query(...),
    connection_method_id: str = Query(...),
    service: ERPConfigService = Depends(get_erp_service),
    db: AsyncSession = Depends(get_db),
) -> CompatibilityResult:
    cache_key = f"compat:{source_product_id}:{target_product_id}:{connection_method_id}"
    cached = service.get_cached_compat(cache_key)
    if cached is not None:
        return cached
    repo = ERPCompatibilityRepository(db)
    is_compatible, message = await repo.check_compatibility(
        source_product_id, target_product_id, connection_method_id
    )
    result = CompatibilityResult(is_compatible=is_compatible, message=message)
    service.set_cached_compat(cache_key, result)
    return result
```

- [ ] **Step 4: Register `compat_router` in `main.py`**

Add import in `src/main.py`:
```python
from src.modules.erp.routes import compat_router
```

Add registration after existing `app.include_router(erp_router)`:
```python
app.include_router(compat_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest src/tests/test_erp/test_erp_routes.py -k "compatibility" -v`
Expected: 2 PASSED

- [ ] **Step 6: Run full ERP test suite to check no regressions**

Run: `uv run pytest src/tests/test_erp/ -v`
Expected: all PASSED

- [ ] **Step 7: Ruff + mypy check**

Run: `uv run ruff check src/ && uv run ruff format src/ --check && uv run mypy src/ --ignore-missing-imports`
Expected: no errors

- [ ] **Step 8: Commit**

```bash
git add src/modules/erp/routes.py src/main.py src/tests/test_erp/test_erp_routes.py
git commit -m "feat(erp): add GET /api/v1/erp/compatibility-check endpoint with 300s TTL cache"
```
