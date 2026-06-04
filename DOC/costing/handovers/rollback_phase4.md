# Phase 3.5/4 Rollback Plan

1. **Disable Integrations**
   - Set `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true` in the deployment env.
   - Optionally clear `MESSAGE_BUS_BROKER` & `BENCHMARK_API_BASE_URL` to force mock behavior.
   - Redeploy service (zero-downtime rolling restart).
2. **Executor**
   - Notify downstream teams that exports are temporarily mocked.
   - Monitor `/metrics` to confirm `planner_executor_requests_total{status="mock"}` increments.
3. **Benchmark**
   - Cache continues serving last successful responses; no action required besides toggling flag.
4. **Message Bus**
   - When broker offline, logs note `message_bus_fallback`. After rollback, events stay in process memory until persistence restored.
5. **Data**
   - No schema rollback required; new tables (`scenario_favorites`, `benchmark_favorites`, `planner_executor_callbacks`) are additive.
6. **Restoration**
   - Revert env flag, reapply real credentials, rerun `backend/scripts/validate_env.py --env-file .env` before redeploy。
