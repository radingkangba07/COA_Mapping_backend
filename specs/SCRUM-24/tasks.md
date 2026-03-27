# Tasks: SCRUM-24 — Make source_erp/target_erp Optional & Add company_name

**Input**: `specs/SCRUM-24/SCRUM-24-optional-erp-company-name.md`
**Prerequisites**: CLAUDE.md, running MongoDB instance, existing `feat/project-crud-endpoints` branch
**Reference**: `backend/server.py`, `backend/services/project_service.py`, `backend/repositories/project_repository.py`, `backend/repositories/company_repository.py`

**Tests**: Manual end-to-end verification via curl (Phase 1). No automated tests — legacy backend has no test suite.

**Organization**: Tasks grouped by implementation phase. Tasks marked [P] within a phase can run in parallel.

## Format: `[ID] [P?] [Phase] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase
- **[Phase]**: Which phase this task belongs to (e.g., Ph0, Ph1, Ph2)
- Include exact file paths relative to repo root in descriptions

## Path Conventions

- **Target code**: `backend/` — legacy MongoDB monolith (all edits happen here)
- **Read-only**: `backend/repositories/company_repository.py` — verify only, no modifications

---

## Phase 0: Code Changes

**Purpose**: Update Pydantic model, route handlers, service layer, and repository to make ERP fields optional and propagate `company_name`.

**Deliverable**: All 3 files modified, backward-compatible API accepting new payload shapes.

### Wave 0 — Schema + Repository (parallel, no cross-file deps)

- [x] T01 [P] Update `ProjectCreate` Pydantic model in `backend/server.py` (lines 192-197). Change `source_erp: str` → `source_erp: Optional[str] = ""`. Change `target_erp: str` → `target_erp: Optional[str] = ""`. Add `company_name: Optional[str] = None` between `company_id` and `description`. Result: 6-field model with 3 required (`name`, `company_id`) and 4 optional

- [x] T02 [P] Update dashboard create endpoint in `backend/server.py` (lines 278-285). Add `company_name=data.company_name` as final kwarg to the `services["project"].create_project()` call inside `POST /api/v1/dashboard/projects` handler

- [x] T03 [P] Update direct create endpoint in `backend/server.py` (lines 446-453). Add `company_name=data.company_name` as final kwarg to the `services["project"].create_project()` call inside `POST /api/v1/projects` handler

- [x] T05 [P] Update `ProjectRepository.create_project()` signature in `backend/repositories/project_repository.py` (lines 31-39). Change `source_erp: str` → `source_erp: str = ""`. Change `target_erp: str` → `target_erp: str = ""`. No other changes — the method body and document structure remain identical

**Checkpoint**: `backend/server.py` accepts POST without `source_erp`/`target_erp` (no 422). `backend/repositories/project_repository.py` defaults ERP fields to `""`.

### Wave 1 — Service Layer + Verification (depends on Wave 0)

- [x] T04 Update `ProjectService.create_project()` in `backend/services/project_service.py` (lines 22-37). Add `company_name: Optional[str] = None` parameter after `description` in the method signature. Change line 37 from `await self.company_repo.get_or_create(company_id)` to `await self.company_repo.get_or_create(company_id, name=company_name)`. No other changes to the method body

- [x] T06 [P] Verify `CompanyRepository.get_or_create()` in `backend/repositories/company_repository.py` (lines 45-58). Confirm it already accepts `name: Optional[str] = None` and falls back to `company_id.replace("-", " ").title()` when `name` is `None`. **No code changes** — this is a read-only verification task

**Checkpoint**: Full call chain works: `server.py` → `project_service.py` → `company_repository.py`. New `company_name` flows from request body to company record creation.

---

## Phase 1: Verification

**Purpose**: End-to-end manual testing to confirm backward compatibility and new functionality.

**Deliverable**: All 7 test scenarios pass, no regressions.

### Wave 0 — End-to-End Tests

- [x] T07 Run manual end-to-end verification against running server (`uvicorn server:app --port 8001`). Test all 7 scenarios:
  - T07.1: `POST /api/v1/projects` with `source_erp` + `target_erp` → 200, project has ERP values (backward compat)
  - T07.2: `POST /api/v1/projects` with only `name` + `company_id` → 200, project has `source_erp: ""`, `target_erp: ""`
  - T07.3: `POST /api/v1/projects` with `company_name: "Acme Corp"` → 200, company record has `name: "Acme Corp"`
  - T07.4: `POST /api/v1/projects` with `company_id: "acme-corp"` (no `company_name`) → 200, company `name` auto-generated as `"Acme Corp"`
  - T07.5: `POST /api/v1/projects` with `company_name` for already-existing company → company record unchanged
  - T07.6: `POST /api/v1/dashboard/projects` with same payloads as T07.1-T07.5 → same results
  - T07.7: `GET /api/v1/projects` after creating with empty ERP → returns `source_erp: ""`, `target_erp: ""`

**Checkpoint**: All 7 scenarios pass. GET endpoints return valid responses with empty ERP strings.

### Wave 1 — Commit & Push

- [ ] T08 Stage exactly 3 files: `backend/server.py`, `backend/services/project_service.py`, `backend/repositories/project_repository.py`. Commit with message referencing SCRUM-24. Push to `feat/project-crud-endpoints`. Verify no unrelated files are included

**Checkpoint**: Commit on `feat/project-crud-endpoints` with only the 3 expected files changed.

---

## Summary

| ID | Phase | Wave | Parallel | File | Change |
|----|-------|------|----------|------|--------|
| T01 | Ph0 | W0 | [P] | `backend/server.py` | Make `source_erp`/`target_erp` optional, add `company_name` to `ProjectCreate` |
| T02 | Ph0 | W0 | [P] | `backend/server.py` | Pass `company_name` in dashboard endpoint |
| T03 | Ph0 | W0 | [P] | `backend/server.py` | Pass `company_name` in direct endpoint |
| T04 | Ph0 | W1 | — | `backend/services/project_service.py` | Add `company_name` param, forward to `get_or_create()` |
| T05 | Ph0 | W0 | [P] | `backend/repositories/project_repository.py` | Default `source_erp=""`, `target_erp=""` |
| T06 | Ph0 | W1 | [P] | `backend/repositories/company_repository.py` | Verify only — no code changes |
| T07 | Ph1 | W0 | — | — | Manual end-to-end verification (7 scenarios) |
| T08 | Ph1 | W1 | — | — | Commit and push to branch |

**Total: 8 tasks, 3 files modified, 0 new files.**