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
| `YIDA_PREFER_LOCAL_BOM_FLAG` | `true` | 当地维护 BOM 标记时是否禁止 YiDa 覆盖 |
| `DINGTALK_APP_KEY` |  | 钉钉应用 AppKey（下载宜搭附件、图片代理） |
| `DINGTALK_APP_SECRET` |  | 钉钉应用 AppSecret |
| `DINGTALK_BASE_URL` | `https://oapi.dingtalk.com` | 钉钉开放平台基础域名（`gettoken`） |
| `DINGTALK_API_BASE_URL` | `https://api.dingtalk.com` | 调用 `v1.0/yida/apps/temporaryUrls/{appType}` 时使用的域名 |
| `DINGTALK_ATTACHMENT_BASE_URL` | `https://appcenter.dingtalk.com` | 非 YiDa 链接的备用前缀 |
| `DINGTALK_APP_TYPE` | _(可选)_ | 覆盖 YiDa `appType`（默认从 `yida_*.json` 读取） |
| `DINGTALK_SYSTEM_TOKEN` | _(可选)_ | 覆盖 YiDa `systemToken`（默认从 `yida_*.json` 读取） |
| `DINGTALK_USER_ID` | _(可选)_ | 请求 temporaryUrls 接口时附带的 `userId` |
| `DINGTALK_CACHE_DIR` | _(可选)_ | 本地图片缓存目录（如 `backend/.cache/dingtalk`） |
| `DINGTALK_CACHE_TTL_SECONDS` | `3600` | 缓存有效期，过期后会重新向钉钉拉取 |
| `PLANNER_MEDIA_DIR` | `backend/media` | 本地媒体落盘目录（用于“图片永久落盘”，默认相对仓库根目录解析） |
| `PLANNER_PERSIST_MATERIAL_IMAGES` | `true` | 是否在读取/同步物料图片时将图片持久化到本地媒体目录（true=永久落盘） |

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

- `materials` – 从宜搭/ERP 同步的基础物料，包含 `material_type`（主料/辅料等）、采购/库存单位、换算公式、供应商信息以及 `calculation_method`（面积/周长/数量/宽度/高度，用于确定默认 BOM 单位）；`metadata` 保留额外来源字段。
- `virtual_materials` & `virtual_material_bindings` – 虚拟物料以及它与真实物料之间的拆解比例（`quantity_ratio`、`loss_rate`），仅记录名称/单位/状态等基础信息，度量方式由调用方在具体使用场景中指定。用于一个虚拟部件映射多种实际物料。
- `process_modules` / `process_module_materials` / `process_module_steps` – 工艺模块与其子项清单：模块表保存基础信息/状态/标签；`process_module_materials` 记录所需物料（可引用真实/BOM/虚拟物料，含数量、损耗、计量口径、材料分类/选材/耗损备注等）；`process_module_steps` 记录工序步骤（顺序、班组、计价方式、工时、单位、说明），同时允许关联全局工序并在 metadata 中保留引用快照。
- `processes` – 工序主数据（支持从宜搭同步或本地维护）：字段包括 `process_code/process_name/category/team_name`、`charging_mode`（fixed/count/area/perimeter/width/height）、`standard_rate`（统一以分钟或单价为标准单位）、`unit_of_measure`、`status/is_active`、`metadata_json`（保留来源表单/自定义字段），供工艺模块与产品模型复用。
- `product_models` – 产品模型主档（标准尺寸、计算模式、固定价格等）。
- `model_materials` – 模型物料清单。**关键字段**：`material_type`（`real` / `virtual`）+ `material_ref_id`（指向 `materials.id` 或 `virtual_materials.id`），配合 `calculation_method`（perimeter/area/count）和 `base_quantity` / `loss_rate` 用于尺寸公式化计算。
- `model_processes` – 模型引用的工序列表（带 `sequence_order`）。
- `model_variant_rules` – 变体规则定义，存储触发条件（字符/面积/周长）与动作（替换/新增），同样使用 `*_material_ref_id` 记录目标物料。
- `product_model_line_variants` / `product_model_line_variant_items` – 标准版本“行级变体”配置：每条 `product_model_line_variants` 绑定某个 `model_version_materials` 行（锚点），保存优先级、启用标记、命中条件 JSON（`spec_contains_any/all`、`*_between`）以及动作（`replace_bundle` / `remove_self` / `add_siblings`）。命中后由 `product_model_line_variant_items` 提供输出物料清单（支持多行、顺序、自定义计量方法与固定用量），便于在订单侧按规则替换/追加。
- `sku_model_mapping` – SKU ↔ 模型绑定（含来源系统、启用状态）。
- `material_sync_jobs` – 记录宜搭物料同步异步任务（job_type、limit、dry_run、result）。
- `code_counters` – 中央编码号段表，按 `prefix` 保存 `next_value`，由自动编码器占用并写回，保证并发场景下的唯一性（详见 Codes API）。

这些表暂未暴露 API，只在 Phase1+ 任务中启用；但可以提前通过 SQL/脚本写入基础数据。

#### Phase‑0 物料数据模型说明

核心字段（`materials` 表）：

| 字段 | 说明 | YiDa / 上游字段 |
| --- | --- | --- |
| `material_code` | 物料唯一编码（与 YiDa 表单、ERP 物料号对齐） | `textField_t8mr6sp` |
| `material_name` | 物料中文名称 | `textField_n5t5vhf` |
| `material_type` | 物料类别：主料/辅料/包装/工序耗材等；前端筛选 & 模型 BOM 公式使用 | `radioField_lxmp8bgd` |
| `category` / `model_category` | 业务分类 / 模型归属，支持画艺、布艺等分组 | `radioField_loo2c67p` + 自定义映射 |
| `calculation_method` | 计价方式（面积/周长/数量/宽度/高度），驱动默认 BOM 单位/模型计量 | 本地维护 |
| `unit` / `purchase_unit` / `inventory_unit` | 计价、采购、库存单位，配合 `conversion_rate` 做换算 | `selectField_lxo1y6ac`、`selectField_looc8l2j` 等 |
| `conversion_purchase_to_bom` / `conversion_bom_to_inventory` | 单位换算（采购→BOM、BOM→库存），默认 1.0，可由本地维护 | 本地维护；宜搭 `textField_m3pgyx4d` 仅用于说明 |
| `metadata_json.bom_unit_price` | 由前端根据采购单价与换算实时推算并落库，供库存单价与 UI 显示使用 | 本地维护 |
| `unit_price` + `currency` | 默认含税单价及币种 | `numberField_lxmosz1s` + `currency` |
| `supplier_name` / `supplier_code` | 默认供应商名称、编码 | `textField_lxmo633k` 等 |
| `status` + `is_active` | 物料启用状态，`PATCH /base-config/materials/{id}` 用于启/停；`status=active` 表示可被模型引用 | API 控制，不随同步覆盖 |
| `is_bom_material` | 是否在本地维护 BOM 单价/单位，前端允许人工勾选；YiDa 仅作为初始值 | `radioField_lxo4jeon` |
| `material_images` | 物料图片列表，仅展示用途，API 会下发 `/base-config/materials/{id}/images/{idx}` 代理路径 | `imageField_lbef2r0b`（宜搭/钉钉附件，原始值是 `/ossFileHandle?...` 相对路径，需走钉钉 `temporaryUrls` 接口换临时下载 URL） |
| `usage_scope` / `bom_notes` | 物料使用场景、BOM 备注 | `textareaField_*` |
| `metadata_json` | `source_form_instance_id` 与 `raw_form_data` 全量备份，方便追溯 | `raw_form_data` JSON |

关联关系与启用规则：

- `model_materials.material_type` + `material_ref_id` 判断引用真实物料 (`real` → `materials.id`) 还是虚拟物料 (`virtual` → `virtual_materials.id`)；禁用真实物料会阻挡模型启用。
- `virtual_material_bindings` 记录虚拟物料拆解成多个真实物料的配比（`quantity_ratio`、`loss_rate`），供后续工序计算。
- `status/is_active` 仅由人工操作或 API 修改，YiDa 同步不会覆盖，避免上线后被表单误改。

YiDa 对接与同步：

- `backend/config/yida_materials.json` 维护 `form_uuid`、字段 ID → 数据库列的映射；脚本 `scripts/sync_yida_materials.py` 与 API `/api/planner/base-config/materials/sync-yida` 共用该配置，可 dry-run。
- 每次同步都会写入 `material_sync_jobs`，`result_json` 中包含 `total_fetched/created/updated/disabled/errors`，可通过 `/materials/sync-jobs` 追溯。
- 缺失字段或新增枚举会完整保存在 `metadata_json.raw_form_data`，便于后续扩展映射。
- `YIDA_PREFER_LOCAL_BOM_FLAG`（默认 true）用于控制 YiDa 是否覆盖本地 `is_bom_material`，为 true 时仅当数据库字段为空才会被远端值刷新。
- 物料图片下载遵循钉钉“获取附件临时免登地址”流程：代理会先用 `https://oapi.dingtalk.com/gettoken` 获取 access token，再调用 `https://api.dingtalk.com/v1.0/yida/apps/temporaryUrls/{appType}`，把 YiDa 的 `/ossFileHandle?...` 作为 `fileUrl` 换成短期有效的 OSS 链接后返回。若配置了 `DINGTALK_CACHE_DIR`，后端会把图片落盘并按 `DINGTALK_CACHE_TTL_SECONDS` 缓存，避免重复请求钉钉；如需自定义下载域名，可通过 `DINGTALK_ATTACHMENT_BASE_URL` 覆盖。
- 图片代理接口：`GET /api/planner/base-config/materials/{id}/images/{idx}` 会优先读取 `materials.metadata_json.local_images` 对应的本地文件；若不存在则回退从钉钉拉取并在 `PLANNER_PERSIST_MATERIAL_IMAGES=true` 时写入本地（默认开启），同时把本地路径写回 `metadata_json.local_images`。本地文件默认存储在 `PLANNER_MEDIA_DIR/material_images/{material_id}/...`。

##### 虚拟物料（Virtual Materials）API

- `GET /api/planner/base-config/virtual-materials` 支持编码/名称模糊搜索及 status 过滤，分页返回。
- `POST /virtual-materials`、`PATCH /virtual-materials/{id}` 维护虚拟物料主数据（编码、描述、单位、状态、备注、metadata）。
- `PUT /virtual-materials/{id}/bindings` 批量维护虚拟物料与真实物料的绑定，只要真实物料启用且未归档即可（允许 BOM/非 BOM 混用）。保存后会把引用关系写入 `materials.metadata_json.virtual_links` 作为提示，解绑时自动清理。
- `POST /virtual-materials/{id}/deactivate` 快捷停用（status → inactive）。
- `GET /materials/{material_id}/virtual-links` 返回某真实物料被哪些虚拟物料引用（含比例、损耗、状态）。
- `POST /virtual-materials/{id}/inventory-breakdown` 盘点折算：传入虚拟物料数量，同时提供本次计算使用的 `calculation_method` 或 `usage_context`，返回各真实物料的消耗建议（`数量 × quantity_ratio × (1 + loss_rate%)`），便于仓库/计划快速核对。

##### 工序（Processes）API

- `GET /api/planner/processes`：分页查询，支持 `search/status/charging_mode` 过滤。
- `POST /processes`、`PATCH /processes/{id}`：创建/更新工序，字段包含分类、班组、计价模式、标准工时/单价、单位、metadata，所有写操作写入审计日志。
- `POST /processes/{id}/activate|deactivate`、`POST /processes/batch/status`：启停单个或批量工序；批量接口接收 `{ids, status}`。
- `POST /processes/{id}/copy`：复制工序（携带 metadata 与计价字段）。
- `GET /processes/references`：工序选择器数据源，可按 `status/search/charging_mode` 过滤，返回 `ProcessReferenceRead`（含 code/name/mode/rate/unit/team/category）。

##### 工艺模块（Process Modules）API

- `GET /api/planner/process-modules`：分页搜索工艺模块（按编码/名称/状态过滤），仅返回基础信息方便列表展示。
- `POST /process-modules`：创建模块及其子项（物料+工序），校验物料引用（真实/BOM/虚拟）和工序/引用合法性，保存时写入审计日志并保留宜搭导出字段（材料分类、选材、耗损等）。
- `GET /process-modules/{id}` & `/preview`：返回模块详情（含 `process_module_materials`、`process_module_steps`），供详情页与“引用前预览”复用。
- `PATCH /process-modules/{id}`：更新基础信息和子项，同时写入审计日志；`POST /process-modules/{id}/activate|deactivate` 支持启停。
- `POST /process-modules/{id}/copy`：复制模块（含物料/工序清单），可指定新编码/名称/状态，并保留原 metadata；写入 audit。
- `GET /process-modules/references`：为产品模型等调用方提供“模块引用查询”，可按 module_ids/状态/关键字筛选并返回完整物料/工序列表，便于一键带入。

##### 规格解析（Spec Parser）API

- `POST /api/planner/spec/parse`：把原始 `spec_text` 解析为结构化字段，输出 `tokens`（按分号/逗号/斜杠/加号等切分）、`width_cm/height_cm/diameter_cm`、推导的 `area_m2/perimeter_m` 以及 `explanations`（记录每个 token 的来源规则，便于运营复盘）。供 SKU 绑定、行级变体命中、BOM 预演等场景复用。

##### 行级变体（Line Variants）API

- `GET /api/planner/product-model-versions/{version_id}/line-variants?base_line_id=...`：列出某个标准版本下的全部（或指定锚点行）变体，返回 `conditions_json`、动作、`stop_on_hit`、`variant_items` 等配置。
- `POST /product-model-versions/{version_id}/line-variants`：为指定 `model_version_material` 行创建变体（支持 `replace_bundle` / `remove_self` / `add_siblings`），写操作统一落审计日志。
- `GET /line-variants/{variant_id}`、`PATCH /line-variants/{variant_id}`、`DELETE /line-variants/{variant_id}`：查询、更新、归档某条变体。
- `GET|PUT /line-variants/{variant_id}/items`：一次性读取或替换变体输出的物料清单（最简单的“整单覆盖”模式）。

##### 动态 BOM 生成（BOM Generate）API

- `POST /api/planner/bom/generate`：输入 `model_version_id`（或 `sku_code`）、`spec_text`、`quantity`，内部会先解析规格 → 拉取标准版本行 → 按锚点/优先级执行行级变体 → 输出 `final_material_lines`（含来源、计量、最终计算数量）和 `trace`（命中规则及顺序）。ADD 类变体默认插在锚点行之后；replace/remove 会替换或删掉锚点行。

##### 编码生成器（Codes API）

- `POST /api/planner/codes/next`：传入 `prefix`（<=16 字符）与 `width`（默认 5，最大 16），原子性地分配下一个编码，例如 `{ "prefix": "VM", "width": 5 }` → `VM00001`。
- 服务端使用 `code_counters` 表 `SELECT ... FOR UPDATE` 锁行，自动插入不存在的前缀并在同一事务中递增 `next_value`，避免并发冲突。
- 适用于虚拟物料、工艺模块、工序等需要顺序号段的场景；前端可直接调用以填充“编码”输入框，也可在批量导入/脚本里复用。

## Scripts & Tests

```bash
cd backend
pytest tests/planner -q                      # 回归套件
python scripts/validate_env.py --env-file ../.env   # 环境检查
python scripts/run_load_test.py                      # 500 并发压测（mock 集成）
python scripts/sync_yida_materials.py --dry-run --limit 20
python scripts/sync_yida_processes.py --dry-run --limit 5
PYTHONPATH=$(pwd) python scripts/export_material_categories.py           # 导出物料分类
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
