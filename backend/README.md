# Planner Backend

FastAPI service that powers the costing planner module (initiatives, packages, line
items, supplier quotes, assumptions, CSV import jobs, scenario snapshots/diffs,
approvals、exports、benchmark hook、审计日志).

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

Default API prefix: `/api/planner`. Health check lives at `/api/planner/health`.

## Configuration

| Env var | Default | Description |
| --- | --- | --- |
| `PLANNER_DATABASE_URL` | `sqlite:///./planner.db` | SQLAlchemy connection string |
| `PLANNER_API_PREFIX` | `/api` | Prefix mounted before `/planner` routes |
| `PLANNER_IMPORT_CHUNK_SIZE` | `500` | Commit interval for CSV import job |
| `EXECUTOR_BASE_URL` | `http://localhost:9100` | External costing executor endpoint |
| `EXECUTOR_API_KEY` | `None` | Optional bearer token for executor |
| `EXECUTOR_CALLBACK_URL` | `http://localhost:8000/api/planner/executor/callback` | Callback URL registered to executor |
| `EXECUTOR_CALLBACK_SECRET` | `executor-secret` | HMAC secret for validating executor callbacks |
| `BENCHMARK_API_BASE_URL` | `http://localhost:9200` | AI benchmark provider base URL |
| `BENCHMARK_API_KEY` | `None` | Optional benchmark service key |
| `BENCHMARK_CACHE_TTL_SECONDS` | `300` | TTL for benchmark suggestions cache |
| `MESSAGE_BUS_BROKER` | `None` | Kafka/RabbitMQ broker URI (falsy → in-memory fallback) |
| `MESSAGE_BUS_TOPIC` | `planner.events` | Topic name for planner notifications |
| `PLANNER_METRICS_ENABLED` | `true` | Toggle Prometheus `/metrics` endpoint |
| `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS` | `false` | Force executor/benchmark/message bus into mock mode |
| `PLANNER_REDIS_URL` | `None` | Optional Redis cache DSN（当前使用内存 TTLCache，可后续切 Redis） |
| `YIDA_MATERIALS_CONFIG_PATH` | `backend/config/yida_materials.json` | 宜搭物料表单凭证/字段映射 |
| `YIDA_PROCESSES_CONFIG_PATH` | `backend/config/yida_processes.json` | 宜搭工序/人工表单凭证/字段映射 |

## Database & migrations

Alembic is configured under `backend/migrations`.

```bash
cd backend
alembic upgrade head        # create all planner tables
alembic revision --autogenerate -m "desc"  # for future changes
```

The migrations create initiatives, packages, line items, supplier quotes,
assumptions, scenarios, approvals, attachments、planner job tables
(`planner_import_jobs`) with multiple job types (`line_item_import`,
`scenario_snapshot`, `scenario_diff`, `scenario_export`), plus `audit_logs`
与 YiDa 同步作业表 `material_sync_jobs`（存储 `/base-config/materials/sync-yida`
触发的后台 Job 状态）。

### Costing core base schema (Phase 0)

`alembic upgrade head` 现在还会创建成本核算核心表（`0005_costing_core_base`）：

- `materials` – 从宜搭/ERP 同步的基础物料，包含 `material_type`（主料/辅料等）、采购/库存单位、换算公式与供应商信息；`metadata` 保留额外来源字段。
- `virtual_materials` & `virtual_material_bindings` – 虚拟物料以及它与真实物料之间的拆解比例（`quantity_ratio`、`loss_rate`）。用于一个虚拟部件映射多种实际物料。
- `process_modules` / `processes` – 工艺模块与工序主数据。模块可复用物料+工序组合，工序记录固定工时、计件单价、质检/班组说明。
- `product_models` – 产品模型主档（标准尺寸、计算模式、固定价格等）。
- `model_materials` – 模型物料清单。**关键字段**：`material_type`（`real` / `virtual`）+ `material_ref_id`（指向 `materials.id` 或 `virtual_materials.id`），配合 `calculation_method`（perimeter/area/count）和 `base_quantity` / `loss_rate` 用于尺寸公式化计算。
- `model_processes` – 模型引用的工序列表（带 `sequence_order`）。
- `model_variant_rules` – 变体规则定义，存储触发条件（字符/面积/周长）与动作（替换/新增），同样使用 `*_material_ref_id` 记录目标物料。
- `sku_model_mapping` – SKU ↔ 模型绑定（含来源系统、启用状态）。
- `material_sync_jobs` – 记录宜搭物料同步异步任务（job_type、limit、dry_run、result）。

这些表暂未暴露 API，只在 Phase1+ 任务中启用；但可以提前通过 SQL/脚本写入基础数据。

## Scripts & Tests

```bash
cd backend
pytest tests/planner -q                      # 回归套件
python scripts/validate_env.py --env-file ../.env   # 环境检查
python scripts/run_load_test.py                      # 500 并发压测（mock 集成）
python scripts/sync_yida_materials.py --dry-run --limit 20
python scripts/sync_yida_processes.py --dry-run --limit 5
```

测试会自动启动 SQLite。`run_load_test.py` 默认使用 mock executor/benchmark，并输出
Scenario Export / Benchmark Suggest 的统计指标，便于比对调参效果。

## Key modules

- `src/main.py` – FastAPI app factory + router mounting.
- `src/planner/models.py` – SQLAlchemy models.
- `src/planner/routers/*` – Initiatives, packages, line items, supplier quotes,
  CSV import, assumptions, scenarios（列表/收藏/clone/diff/export + 回调）、approvals、
  benchmark suggest & favorites、job status、executor callbacks。
- `src/planner/services/import_service.py` – background CSV ingestion worker。
- `src/planner/services/quote_service.py` – supplier quote validation helpers。
- `src/planner/services/snapshot_service.py` – scenario cloning + diff logic。
- `src/planner/services/notification_service.py` – 统一向 Kafka/RabbitMQ（或内存落地）
  的事件发布器。
- `src/planner/services/audit_service.py` – helper for inserting audit logs + trace_ids。
- `src/planner/integrations/executor_client.py` – 真实执行器 HTTP 客户端（重试、断路器、Trace ID）。
- `src/planner/integrations/benchmark_client.py` – AI Benchmark API 代理（支持缓存）。
- `src/planner/integrations/message_bus.py` – Kafka/RabbitMQ 生产者（无配置时降级为内存队列）。
- `src/planner/services/metrics.py` – Prometheus Counter/Histogram 及 `/metrics` endpoint。
- `src/planner/services/yida_sync.py` – 宜搭物料/工序同步逻辑：MaterialSyncService、ProcessSyncService、MaterialSyncJob runner。

## Runbooks & Docs
- Monitoring & Grafana: `DOC/costing/manuals/monitoring_setup.md`
- Trace/Audit 查询流程: `DOC/costing/manuals/trace_runbook.md`
- Benchmark 降级/feature flag：`BENCHMARK_FAIL_OPEN` 控制 fail-open；
  如需完全 mock 可设置 `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true`。
- 回滚方案: `DOC/costing/handovers/rollback_phase4.md`
- YiDa 定时同步：`DOC/costing/runbooks/yida_sync_scheduler.md`（systemd timer / cron 示例，含 `/ops/systemd/*.service|timer`）
