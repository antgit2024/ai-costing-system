# Frontend Briefing – Phase 4 (UAT & Performance)

### Branch
- `feature/costing-frontend-phase4` (based on latest `feature/costing-frontend`).

### Objectives
- Validate Planner UI against staging APIs with production configs, reduce bundle size, and finalize documentation.

### Scope
1. **Env & Build Profiles**
   - Provide `.env.production.example` with API base URLs, SSE/WebSocket (if any), feature flags for executor/benchmark.
   - Update README with build/run commands for staging vs production (npm scripts + Vite config).

2. **Performance Optimization**
   - Analyze `frontend/dist/stats.html`, split shared dependencies (e.g., AntD icons, moment) using Vite manualChunks.
   - Target: main bundle < 400 kB (gzipped). Document before/after metrics in `DOC/costing/ops/frontend_perf_report.md`.

3. **UAT Flow**
   - Run end-to-end tests on staging: CSV import → clone → diff → approval → export → AI benchmark.
   - Add Cypress/Playwright smoke tests or scripted flows under `frontend/tests/e2e/` (if feasible).
   - Capture screenshots for final manual (with real data).

4. **Observability Support**
   - Ensure Scenario List, Builder, Job Drawer show trace ID / job ID with copy button.
   - Display clear status/state for long-running operations (loading, success, retry).

5. **Docs**
   - Update `DOC/costing/manuals/planner_user_guide.md` screenshots and instructions referencing real staging URLs.
   - Add “Known Issues & Workarounds” section.

6. **Testing**
   - `npm run test -- --run`
   - `npm run build`
   - `npm run build:report` (attach stats)

### Acceptance
- Builds succeed with reduced bundle size, documentation updated, UAT report shared (list of scenarios tested + issues).
- Task log entry describing work + any risks.

### Notes
- Coordinate with Docs/QA for shared screenshots and regression plan.
- Ensure fallbacks for when backend feature flags are off.














