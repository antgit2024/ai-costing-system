# Frontend Briefing – Phase 3.5 Production Experience

### Branch
- `feature/costing-frontend` → create `feature/costing-frontend/phase3-5`.

### Objectives
- Consume new backend capabilities (scene list API, real export, AI benchmark, audit pagination).
- Improve UX around favorites, job tracking, and bundle performance for production rollout.

### Scope
1. **Scene List & Favorites**
   - Implement `/planner/scenarios` page showing table/cards of scenarios with filters (status, owner, favorite, initiative).
   - Call new `/api/planner/scenarios` endpoint with pagination & search.
   - Add favorite toggle that persists via `/scenarios/{id}/favorite`.
   - Provide bulk actions (submit for approval, export) where allowed.

2. **Scenario Builder Enhancements**
   - Replace local scenario cache with API-backed list; ensure clone/export refresh list automatically.
   - Show export history timeline (pull from `/api/planner/audit?target_type=scenario` with pagination).
   - Integrate new message bus events if exposed via SSE/WebSocket placeholder (optional: poll job endpoint).

3. **AI Benchmark**
   - Display real suggestions from `/api/planner/benchmarks/suggest` including metadata (supplier, cost, confidence).
   - Allow users to pin favorites, persisted via `/benchmarks/favorites`.
   - Provide status indicator for data freshness; add tooltip referencing data source.

4. **PlannerJobDrawer & Audit Drawer**
   - Lazily load drawers (React.lazy + Suspense) to reduce initial bundle.
   - Add pagination/search for audit logs, support trace ID filter.
   - Job drawer shows trace ID, external job refs, and allows copying payload.

5. **Performance**
   - Ensure Scenario Builder chunk < 120 kB, Planner main chunk < 350 kB (report numbers in PR).
   - Use `vite-plugin-imp` or `babel-plugin-import` to ensure AntD components are tree-shaken.
   - Add dynamic import for large charts/tables if needed.

6. **Docs & Tests**
   - Update `frontend/README.md` and `DOC/costing/manuals/planner_user_guide.md` screenshots/steps (coordinate with Docs Agent).
   - Add tests for favorites persistence, scene list filters, benchmark pinning.
   - Run `npm run test -- --run` and `npm run build`; attach bundle stats summary.

### Dependencies
- Backend Phase 3.5 endpoints (`/api/planner/scenarios`, `/favorite`, `/benchmarks/*`), message bus events (if exposed).
- Ensure `.env` includes new base URLs or feature flags (document in README).

### Acceptance Criteria
- Scene list + favorites fully functional with API pagination.
- Scenario Builder uses API-sourced data; export/audit timelines visible.
- AI benchmark panel shows real data and sticky favorites.
- Drawers lazy-loaded, audit pagination works, job drawer shows trace IDs.
- Tests + build succeed; documentation updated; task log entry added.

### Risks / Notes
- Handle slow `/scenarios` responses with skeleton/loading states.
- Gracefully fall back to mock data if backend feature flag disabled.
- Keep accessibility (keyboard navigation, ARIA) for new drawers and tables.














