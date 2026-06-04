# Backend Briefing – Phase 3.5 Production Integrations

### Branch
- `feature/costing-backend` → create sub-branch `feature/costing-backend/phase3-5` for this work.

### Goals
- Replace Phase 3 mocks (executor client, AI benchmark hook, notifications) with production-ready integrations.
- Provide scene list/favorites API and persistence needed by frontend.
- Ensure observability/auditing meets rollout requirements.

### Scope
1. **Executor Integration**
   - Implement real client (HTTP or gRPC) under `backend/src/planner/integrations/executor_client.py`.
   - Support retries, exponential backoff, timeout, and circuit breaker (fastapi-limiter or custom).
   - Add `executor_callback_url` config + signature verification for callbacks (store in `planner_executor_callbacks` table).
   - Export API (`/api/planner/scenarios/{id}/export`) now enqueues real jobs; record success/failure with trace IDs.

2. **Scenario Listing API**
   - New router `/api/planner/scenarios` with filters: initiative_id, status, baseline_flag, favorite, text search.
   - Add `scenario_favorites` table referencing user + scenario. Provide `POST/DELETE /scenarios/{id}/favorite`.
   - Ensure pagination + sorting (updated_at desc default).

3. **AI Benchmark Provider**
   - Create `ai_benchmark_client.py` hitting external service (configurable base URL & key).
   - `/api/planner/benchmarks/suggest` now proxies real data, caches responses (Redis/local) for 5 minutes.
   - Add endpoint `/api/planner/benchmarks/favorites` to persist user selections (table `benchmark_favorites`).

4. **Notifications & Message Bus**
   - Introduce `notification_service.py` that publishes to Kafka/RabbitMQ topic `planner.events` (config via env).
   - Events: `SCENARIO_APPROVED`, `SCENARIO_EXPORTED`, `SCENARIO_DIFF_READY`.
   - Include payload schema (scenario_id, initiative_id, actor_id, trace_id, status, metadata).

5. **Observability**
   - All jobs & external calls log `trace_id` (UUID v4) stored in `audit_logs`.
   - Add metrics exporter (Prometheus endpoints) counting success/failure per integration.

6. **Migrations**
   - Create `backend/migrations/versions/0004_phase35_integrations.py` for new tables/columns (favorites, callbacks).

7. **Testing**
   - Add integration tests with mock servers (use `respx` or `httpx_mock`) for executor + benchmark.
   - Extend existing tests to cover scenario list filters, favorites, notification events.
   - Update README with env vars (`EXECUTOR_BASE_URL`, `BENCHMARK_API_KEY`, `MESSAGE_BUS_BROKER`, etc.).

### Out of Scope
- Real AI model training or heavy analytics.
- UI changes (handled by frontend).
- Production infra provisioning (but configs/documentation must be ready).

### Acceptance Criteria
- `pytest tests/planner -q` passes with new coverage.
- New endpoints documented in README and `DOC/costing/architecture.md`.
- Message bus publisher tested via fake broker.
- Task log updated after completion with summary + risks.

### Commands
- `cd backend && source .venv/bin/activate`
- `alembic upgrade head`
- `pytest tests/planner -q`
- `uvicorn src.main:app` (optional manual verification)

### Risks / Checks
- Ensure secrets not logged.
- Provide feature flag/env toggle for legacy mock vs real client.
- Define rollback plan in docs (disable feature flag, revert env vars).














