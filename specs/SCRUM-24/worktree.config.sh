#!/bin/bash
# worktree.config.sh — Phase/wave config for SCRUM-24
# Sourced by raulph-worktree.sh via: -config specs/SCRUM-24/worktree.config.sh
#
# SCRUM-24: Make source_erp/target_erp optional, add company_name to project creation
# Spec: specs/SCRUM-24/SCRUM-24-optional-erp-company-name.md

# ─── Project Settings ─────────────────────────────────────────────────────────
INTEGRATION_BRANCH="feat/project-crud-endpoints"
TASKS_FILE="specs/SCRUM-24/tasks.md"
AGENT="senior-python-backend"
REVIEWER="senior-python-backend"
PROGRESS_FILE="specs/SCRUM-24/progress.txt"

# ─── Agent Prompt (appended to the base prompt for every agent) ───────────────
AGENT_PROMPT_EXTRA="
CRITICAL CONSTRAINTS:
- All changes go in backend/ (legacy MongoDB monolith) — NOT in src/ or services/
- This is a targeted change to 3 files only. Do NOT refactor, reorganize, or add extra code.
- Read the full spec at specs/SCRUM-24/SCRUM-24-optional-erp-company-name.md before making any change.
- Each task in specs/SCRUM-24/tasks.md has Before/After code blocks — match them exactly.
- Do NOT modify backend/repositories/company_repository.py — it already works as-is (Task 6 is verify-only).
- Do NOT add docstrings, comments, type annotations, or tests beyond what the task specifies.
- Do NOT commit .agent-*.txt files. Use git add with specific file paths, never git add -A or git add .

FILES IN SCOPE (read-write):
  backend/server.py                          — Tasks 1, 2, 3
  backend/services/project_service.py        — Task 4
  backend/repositories/project_repository.py — Task 5

FILES IN SCOPE (read-only, verify only):
  backend/repositories/company_repository.py — Task 6
"

# ─── Task Ranges ──────────────────────────────────────────────────────────────
# T01-T03: server.py (Pydantic model + both endpoints)
# T04:     project_service.py (service signature + get_or_create call)
# T05:     project_repository.py (ERP param defaults)
# T06:     company_repository.py (verify only — no code changes)
# T07:     End-to-end verification
# T08:     Commit and push
#
# No overlaps: T01-T03 | T04 | T05 | T06 | T07 | T08

MAX_PHASE=2

# ─── Phase 0: Code Changes ───────────────────────────────────────────────────
# Wave 0: server.py edits (T01-T03 must be same agent — same file)
#          + project_repository.py (T05 — independent file, can parallelize)
# Wave 1: project_service.py (T04 — depends on server.py having the new param)
#          + verify company_repository.py (T06 — read-only, no deps)
PHASE_0_WAVES=2
PHASE_0_WAVE_0=(
  "scrum24/server-model-endpoints|T01|T03"
  "scrum24/repo-erp-defaults|T05|T05"
)
PHASE_0_WAVE_1=(
  "scrum24/service-company-name|T04|T04"
  "scrum24/verify-company-repo|T06|T06"
)

# ─── Phase 1: Verification & Commit ──────────────────────────────────────────
# Wave 0: Manual end-to-end verification (T07 — all code must be merged first)
# Wave 1: Commit and push (T08 — only after verification passes)
PHASE_1_WAVES=2
PHASE_1_WAVE_0=("scrum24/e2e-verification|T07|T07")
PHASE_1_WAVE_1=("scrum24/commit-push|T08|T08")

# ─── Phase 2: Reserved ───────────────────────────────────────────────────────
# Empty — available if post-merge fixups are needed
PHASE_2_WAVES=0