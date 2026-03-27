# SCRUM-24: Make source_erp/target_erp Optional & Add company_name to Project Creation

**Jira:** SCRUM-24
**Status:** In Progress
**Priority:** High
**Branch:** `feat/project-crud-endpoints`
**Related:** SCRUM-5 (original request), SCRUM-23 (frontend changes)

---

## 1. Context & Motivation

SCRUM-5 redesigned the "Create New Project" form so that Source ERP and Target ERP are no longer chosen at creation time — they are selected later in the migration wizard's ERPSelect screen. Additionally, a `company_name` field was added to the frontend form so users can supply a human-readable company name instead of relying on auto-generated names from `company_id`.

The backend must be updated to:
1. Accept project creation requests **without** `source_erp` / `target_erp` (backward-compatible — callers that still send them must continue to work).
2. Accept and propagate a new optional `company_name` field so the company record gets a proper display name.

---

## 2. Current State (Before)

### 2.1 Pydantic Model — `ProjectCreate`

**File:** `backend/server.py` (lines 192-197)

```python
class ProjectCreate(BaseModel):
    name: str
    source_erp: str          # REQUIRED
    target_erp: str          # REQUIRED
    company_id: str
    description: Optional[str] = None
    # company_name does NOT exist
```

Both ERP fields are **required strings** — any POST without them returns 422.

### 2.2 Dashboard Endpoint — `POST /api/v1/dashboard/projects`

**File:** `backend/server.py` (lines 269-285)

```python
@api_router.post("/dashboard/projects")
async def create_project(data: ProjectCreate, authorization: ...):
    user_id = await get_current_user_id(authorization)
    services = get_services()
    return await services["project"].create_project(
        name=data.name,
        source_erp=data.source_erp,
        target_erp=data.target_erp,
        company_id=data.company_id,
        created_by=user_id,
        description=data.description
        # company_name NOT passed
    )
```

### 2.3 Direct Endpoint — `POST /api/v1/projects`

**File:** `backend/server.py` (lines 437-453)

```python
@api_router.post("/projects")
async def create_project_direct(data: ProjectCreate, authorization: ...):
    user_id = await get_current_user_id(authorization)
    services = get_services()
    result = await services["project"].create_project(
        name=data.name,
        source_erp=data.source_erp,
        target_erp=data.target_erp,
        company_id=data.company_id,
        created_by=user_id,
        description=data.description
        # company_name NOT passed
    )
```

### 2.4 Service — `ProjectService.create_project()`

**File:** `backend/services/project_service.py` (lines 22-56)

```python
async def create_project(
    self,
    name: str,
    source_erp: str,        # REQUIRED
    target_erp: str,        # REQUIRED
    company_id: str,
    created_by: str,
    description: Optional[str] = None
    # company_name does NOT exist
) -> Dict[str, Any]:
    await self.company_repo.get_or_create(company_id)   # no name passed
    project = await self.project_repo.create_project(
        name=name,
        source_erp=source_erp,
        target_erp=target_erp,
        company_id=company_id,
        created_by=created_by,
        description=description
    )
    await self.access_repo.grant_access(
        user_id=created_by,
        project_id=project["id"],
        permission="admin"
    )
    return {"success": True, "project": project}
```

### 2.5 Repository — `ProjectRepository.create_project()`

**File:** `backend/repositories/project_repository.py` (lines 31-56)

```python
async def create_project(
    self,
    name: str,
    source_erp: str,        # REQUIRED
    target_erp: str,        # REQUIRED
    company_id: str,
    created_by: str,
    description: Optional[str] = None,
    status: str = "draft"
) -> Dict[str, Any]:
    ...
    project = {
        ...
        "source_erp": source_erp,
        "target_erp": target_erp,
        ...
    }
    return await self.insert_one(project)
```

### 2.6 Repository — `CompanyRepository.get_or_create()`

**File:** `backend/repositories/company_repository.py` (lines 45-58)

```python
async def get_or_create(
    self,
    company_id: str,
    name: Optional[str] = None    # Already accepts optional name
) -> Dict[str, Any]:
    company = await self.find_by_company_id(company_id)
    if company:
        return company
    return await self.create_company(
        company_id=company_id,
        name=name or company_id.replace("-", " ").title()   # Falls back to auto-generated
    )
```

**No changes needed** — already supports the optional `name` parameter.

---

## 3. Target State (After)

### 3.1 Updated Pydantic Model — `ProjectCreate`

```python
class ProjectCreate(BaseModel):
    name: str
    source_erp: Optional[str] = ""      # Was required, now optional with "" default
    target_erp: Optional[str] = ""      # Was required, now optional with "" default
    company_id: str
    company_name: Optional[str] = None  # NEW — human-readable company name
    description: Optional[str] = None
```

**Rationale for `Optional[str] = ""`:** Using empty string as default (rather than `None`) ensures the MongoDB document always has string-typed ERP fields, avoiding `None` type-check issues downstream. Callers that still send `source_erp`/`target_erp` are unaffected.

### 3.2 Updated Endpoints (both)

Both `POST /api/v1/dashboard/projects` and `POST /api/v1/projects` add `company_name=data.company_name` to the service call:

```python
return await services["project"].create_project(
    name=data.name,
    source_erp=data.source_erp,
    target_erp=data.target_erp,
    company_id=data.company_id,
    created_by=user_id,
    description=data.description,
    company_name=data.company_name       # NEW
)
```

### 3.3 Updated Service — `ProjectService.create_project()`

```python
async def create_project(
    self,
    name: str,
    source_erp: str,
    target_erp: str,
    company_id: str,
    created_by: str,
    description: Optional[str] = None,
    company_name: Optional[str] = None       # NEW
) -> Dict[str, Any]:
    await self.company_repo.get_or_create(company_id, name=company_name)  # Pass name
    ...
```

### 3.4 Updated Repository — `ProjectRepository.create_project()`

```python
async def create_project(
    self,
    name: str,
    source_erp: str = "",       # Was required, now defaults to ""
    target_erp: str = "",       # Was required, now defaults to ""
    company_id: str = "",
    created_by: str = "",
    description: Optional[str] = None,
    status: str = "draft"
) -> Dict[str, Any]:
    ...
```

### 3.5 No Changes Needed

| File | Reason |
|------|--------|
| `backend/repositories/company_repository.py` | `get_or_create()` already accepts optional `name` param (line 48) and falls back to `company_id.replace("-", " ").title()` |
| MongoDB schema / collections | No schema enforcement — flexible document store, empty string ERP fields are valid |
| GET endpoints | Return whatever is stored; empty ERP strings are valid JSON |
| Frontend (SCRUM-23) | Separate ticket, already handles the new form fields |

---

## 4. Changes Summary

| # | File | Location | Change |
|---|------|----------|--------|
| 1 | `backend/server.py` | Lines 192-197 (`ProjectCreate`) | Make `source_erp`/`target_erp` optional with `""` default; add `company_name: Optional[str] = None` |
| 2 | `backend/server.py` | Lines 278-285 (dashboard endpoint) | Add `company_name=data.company_name` to service call |
| 3 | `backend/server.py` | Lines 446-453 (direct endpoint) | Add `company_name=data.company_name` to service call |
| 4 | `backend/services/project_service.py` | Lines 22-30 (`create_project` signature) | Add `company_name: Optional[str] = None` parameter |
| 5 | `backend/services/project_service.py` | Line 37 (`get_or_create` call) | Pass `name=company_name` |
| 6 | `backend/repositories/project_repository.py` | Lines 31-39 (`create_project` signature) | Default `source_erp=""`, `target_erp=""` |

**Total: 3 files, 6 changes. No new files.**

---

## 5. Data Flow

```
Frontend (SCRUM-23)
  │
  ▼
POST /api/v1/projects
  Body: { name, company_id, company_name?, source_erp?, target_erp?, description? }
  │
  ▼
server.py → ProjectCreate model validates:
  - name: required
  - company_id: required
  - source_erp: defaults to ""
  - target_erp: defaults to ""
  - company_name: defaults to None
  - description: defaults to None
  │
  ▼
ProjectService.create_project(name, source_erp, target_erp, company_id, created_by, description, company_name)
  │
  ├──► CompanyRepository.get_or_create(company_id, name=company_name)
  │       - If company exists → return it (name NOT updated)
  │       - If new → create with company_name or auto-generated fallback
  │
  ├──► ProjectRepository.create_project(name, source_erp="", target_erp="", ...)
  │       - Stores empty strings for ERP fields until set in migration wizard
  │
  └──► ProjectAccessRepository.grant_access(user_id=created_by, permission="admin")
```

---

## 6. Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| Client sends `source_erp` + `target_erp` (old behavior) | Works exactly as before — values passed through the entire chain |
| Client omits `source_erp` + `target_erp` (new behavior) | Defaults to `""` at Pydantic layer; stored as empty strings in MongoDB |
| Client sends `company_name` (new field) | Passed to `CompanyRepository.get_or_create()` for proper display name |
| Client omits `company_name` | `None` → `get_or_create` falls back to `company_id.replace("-", " ").title()` |
| Existing projects with ERP values set | Unaffected — only creation is changed, not reads or updates |

---

## 7. Edge Cases & Considerations

### 7.1 Existing Company with New Name
If `company_id` already exists in the DB, `get_or_create()` returns the existing record **without updating the name**. This is intentional — the first creator's name wins. If name updates are needed later, that's a separate feature.

### 7.2 Empty String vs None for ERP Fields
Using `Optional[str] = ""` means the field type is `Optional[str]` but the practical default is `""`. This ensures:
- MongoDB documents always have `source_erp` and `target_erp` as strings
- No `None`-check needed in downstream code that reads these fields
- JSON serialization returns `"source_erp": ""` (not `null`)

### 7.3 No Validation on ERP Values
When ERP values are provided, no validation is performed against known ERP system IDs. This matches existing behavior. ERP validation happens later in the migration wizard flow.

---

## 8. Verification Plan

| # | Test | Expected Result |
|---|------|-----------------|
| 1 | `POST /api/v1/projects` with `source_erp` + `target_erp` | 200 OK, project created with provided ERP values (backward compat) |
| 2 | `POST /api/v1/projects` without `source_erp` / `target_erp` | 200 OK, project created with `source_erp: ""`, `target_erp: ""` |
| 3 | `POST /api/v1/projects` with `company_name: "Acme Corp"` | Company record created with `name: "Acme Corp"` |
| 4 | `POST /api/v1/projects` without `company_name`, `company_id: "acme-corp"` | Company record created with `name: "Acme Corp"` (auto-generated) |
| 5 | `POST /api/v1/projects` with `company_name` for existing company | Company record unchanged (existing name preserved) |
| 6 | `POST /api/v1/dashboard/projects` — same tests as #1-5 | Same behavior on both endpoints |
| 7 | `GET /api/v1/projects` after creating with empty ERP fields | Returns projects with `source_erp: ""`, `target_erp: ""` |

### Manual Verification Commands

```bash
# Test 1: Full payload (backward compatible)
curl -X POST http://localhost:8001/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Test Project",
    "source_erp": "sap",
    "target_erp": "netsuite",
    "company_id": "test-company",
    "description": "Backward compat test"
  }'

# Test 2: Minimal payload (new behavior)
curl -X POST http://localhost:8001/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Test Project",
    "company_id": "test-company"
  }'

# Test 3: With company_name
curl -X POST http://localhost:8001/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Test Project",
    "company_id": "acme-corp",
    "company_name": "Acme Corporation"
  }'
```

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Downstream code assumes `source_erp` is non-empty | Low | Medium | ERP fields were already string type; empty string is valid. Migration wizard sets them before they're consumed. |
| Company name mismatch (existing company, different name sent) | Low | Low | By design — first name wins. Documented in edge cases. |
| Frontend sends `null` instead of omitting field | Low | Low | Pydantic coerces `null` to the default (`""` / `None`) correctly. |

---

## 10. Dependencies

- **SCRUM-23** (frontend) — Removes ERP fields from create form, adds `company_name`. Should be merged in parallel or after this backend change.
- **SCRUM-5** (parent) — Original request. This ticket implements the backend portion.