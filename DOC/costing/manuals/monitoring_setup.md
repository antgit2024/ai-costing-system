# Planner Monitoring & Alerting Setup

## Prometheus
1. Deploy the FastAPI service with `PLANNER_METRICS_ENABLED=true`.
2. Scrape `http://<planner-host>:8000/metrics` (or whatever port is exposed).
3. Key metrics:
   - `planner_executor_requests_total{status}` – success/failure/circuit counters.
   - `planner_external_call_duration_seconds_bucket{integration}` – latency histograms for executor/benchmark.
   - `planner_message_bus_events_total{event_type}` – event volume per scenario lifecycle.
4. Example scrape config:
   ```yaml
   - job_name: 'planner'
     metrics_path: /metrics
     static_configs:
       - targets: ['planner-api:8000']
   ```

## Grafana Dashboard
Import `monitoring/grafana/planner-integrations.json` and bind it to the Prometheus data source. Panels include executor success/failure counts, benchmark p95 latency, and message bus throughput. Suggested alerts:
- Executor failure rate > 5% for 5 minutes.
- Benchmark p95 latency > 2s.
- Message bus events = 0 while exports are running.

## Alert Routing
- Hook alertmanager routes to #planner-alerts (Slack) and PagerDuty "Costing Planner" service.
- Include trace links by templating annotations with `{{ $labels.trace_id }}` if present.
