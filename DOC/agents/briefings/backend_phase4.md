# Backend Briefing – Phase 4 (Staging & Ops Hardening)

### Branch
- `feature/costing-backend-phase4` (new branch from latest `feature/costing-backend`).

### Objectives
- Prepare backend for production rollout: environment configs, monitoring, load tests, and rollback plan.

### Scope
1. **Environment & Config**
   - Add `.env.sample.prod` documenting EXECUTOR/ BENCHMARK / MESSAGE_BUS / REDIS / CALLBACK secrets.
   - Provide `scripts/validate_env.py` to check mandatory vars and connectivity.
   - Update README with staged vs prod configuration matrix.

2. **Monitoring & Metrics**
   - Extend Prometheus metrics: executor latency/ success/ failure, benchmark cache hits, message bus publish status.
   - Provide Grafana dashboard JSON (save under `DOC/costing/ops/grafana_planner.json`).
   - Ensure `/metrics` endpoint registered in `src/main.py`.

3. **Load / Resilience Testing**
   - Create `tests/perf/export_benchmark_test.py` (pytest + locust or simple loop) hitting staging executor/benchmark with 500 concurrent requests.
   - Document results + tuning decisions in `DOC/costing/ops/phase4_perf_report.md`.

4. **Traceability**
   - Write guide `DOC/costing/ops/trace_playbook.md` explaining how to follow `trace_id` through audit_logs → planner_jobs → logs.
   - Add API to fetch job by trace (`/api/planner/jobs/by-trace/{trace_id}`).

5. **Rollback & Feature Flags**
   - Introduce env toggles `PLANNER_EXECUTOR_ENABLED`, `PLANNER_BENCHMARK_ENABLED`.
   - Document rollback steps in README + handover doc.

6. **Testing**
   - Run `pytest tests/planner -q` plus new perf test (if automated).
   - Verify `alembic upgrade head` still works from clean DB.

### Deliverables
- Updated README, `.env` samples, monitoring dashboards, perf report, trace playbook.
- Task log entry summarizing findings + open risks.

### Commands
- `cd backend && source .venv/bin/activate`
- `pytest tests/planner -q`
- `python scripts/validate_env.py`
- `python tests/perf/export_benchmark_test.py` (or documented load test command)

### Risks
- Access to staging services/credentials required.
- Ensure secrets not committed.














