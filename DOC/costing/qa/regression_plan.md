---
title: Costing Planner Regression Plan
status: v0.1 (2025-12-13)
owner: QA Agent
sample_data: ./sample_data
---

## 1. Dataset Overview

| File | Purpose | Key Columns |
| --- | --- | --- |
| `sample_data/line_items_sample.csv` | Drives import → package distribution | `package_id`, `type`, `quantity`, `unit_cost_estimate`, `metadata` |
| `sample_data/assumptions_sample.csv` | Seeds FX / inflation inputs for scenarios | `type`, `value`, `effective_date` |
| `sample_data/scenarios_sample.csv` | Provides baseline + variants for clone/diff/export | `status`, `baseline_flag`, `total_cost` |

### Test DB Seeding
1. Create initiative `INIT-NEO-2025` and packages (`PKG-*`) per requirements doc.
2. Load line items via `/line-items/import` using the CSV (expect 6 rows, zero errors).
3. Insert assumptions and scenarios via API or SQL migration script.

## 2. Regression Matrix

| ID | Flow | Steps | Expected Result |
| --- | --- | --- | --- |
| REG-CLONE-001 | Scenario clone baseline | `POST /scenarios/{SCN-BL-2025A}/clone` with new `code=ALT-2025B-CLONE`, subset of line items | Job completes with `status=completed`, new scenario inherits selected lines, audit log contains `scenario_clone` entry |
| REG-DIFF-002 | Scenario diff variance | `GET /scenarios/{SCN-ALT-2025B}/diff?against=SCN-BL-2025A&type=material` | Response summary variance matches manual spreadsheet (use dataset values), job result totals persisted |
| REG-APPROVE-003 | Submit + approve | Submit `SCN-SUP-REDUCE`, approve with `set_baseline=false` | Scenario status transitions: `draft → in_review → approved`, `approval_records` captures both actions |
| REG-EXPORT-004 | Approved export | Export `SCN-BL-2025A` | API gate enforces status, job returns `executor_reference`, audit log entry `scenario_export` created |
| REG-AUDIT-005 | Audit replay | Call `/audit` for `SCN-BL-2025A` after clone/diff/export | Timeline contains ordered actions; payload includes job ids used for traceability |
| REG-AI-006 | Benchmark suggest | `POST /benchmarks/suggest` with `scenario_id=SCN-ALT-2025B` | Returns >=3 records, each with `id/title/impact/recommendation`; UI favorites toggle updates state only |
| REG-IMPORT-007 | Line import validation | Upload CSV with 1 invalid row (e.g., missing `package_id`) | Job transitions to `completed_with_errors`, `errors` array logs row + reason |
| REG-APPROVAL-GUARD-008 | Export guard | Try exporting `SCN-ALT-2025B` (draft) | API returns 400 with message “Scenario must be approved before export”, no job created |

## 3. Execution Checklist

- [ ] Refresh DB with sample dataset snapshot.
- [ ] Run automated API tests (pytest) covering routers touched above.
- [ ] Execute manual UI scripts:
  1. Import CSV and verify `PlannerJobDrawer` metrics.
  2. Clone baseline and confirm new scenario card rendering.
  3. Run diff and capture screenshot for release notes.
  4. Submit/approve/export chain while keeping job drawer open.
  5. Validate AI suggestions/favorites.
  6. Download audit JSON and attach to QA evidence.
- [ ] Record findings in `DOC/agents/task_log.md`.

## 4. Tooling Notes

- **API Client**: Use `frontend/src/services/planner.ts` signatures to avoid payload drift.
- **Automation Hooks**: Scenario export and diff already return `job_id`; reuse `usePlannerJob` polling for UI tests.
- **Rollback**: Use `planner_import_jobs` and `audit_logs` to confirm cleanup or to reset between runs.

## 5. Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| CSV import drift (new columns) | Keep sample CSV minimal; rely on DictReader to ignore extra headers |
| Scenario totals mismatch | Store manual calculation spreadsheet with dataset; compare totals before/after diff |
| Executor integration unavailable | Mock response already in `executor_client`; tests assert presence of `reference_id` only |
| Audit log volume | Paginate UI drawer (already supported) or filter by date if >200 records |















