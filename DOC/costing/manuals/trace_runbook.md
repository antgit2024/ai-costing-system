# Planner Trace & Troubleshooting Runbook

## Trace ID Sources
- Every scenario clone/diff/export/approval emits a `trace_id` (UUID v4).
- Stored in `audit_logs.trace_id`, `planner_executor_callbacks.trace_id`, Prometheus labels (`planner_executor_requests_total{trace_id}` via logs), and Kafka payloads.
- Notifications (Kafka + in-memory) include the same trace ID for correlation.

## Trace Lookup Flow
1. **From Alert**: Grab the `trace_id` from alert annotations or Grafana panel hover.
2. **Audit Log**: `SELECT * FROM audit_logs WHERE trace_id = '<trace_id>';` – shows scenario, actor, and action timeline.
3. **Job Table**: `planner_import_jobs` records include payload/result; filter by `payload ->> 'trace_id'` when applicable.
4. **Executor Callback**: `planner_executor_callbacks` stores callback status/signature. Join by trace to ensure callback arrived.
5. **Application Logs**: Search structured logs for `trace_id=<value>` to retrieve FastAPI request logs.

## Common Scenarios
- **Export stuck**: audit shows `scenario_export` but no `executor_callback` – check message bus events for `SCENARIO_EXPORTED`, re-deliver to executor if necessary.
- **Benchmark latency**: look at Grafana p95 panel, cross-check `benchmark_requests_total` for failure spikes.
- **Rollback**: set `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true` and restart service; executor/benchmark/message bus revert to in-process mocks, preserving API contract.
