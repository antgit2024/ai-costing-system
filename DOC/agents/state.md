## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-23 20:05（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **分支**：`backup/20251214-1535`

- **本轮闭环产物（Planner-Optimization / 方案评审稿）**：
  - `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`（回答：SKU_NOT_BOUND 根因与治理、spec_hash+解析版本化、幂等与重试/重跑语义、UI按Excel展示）
  - 验收命令：`grep -nF "发货时再解析（spec_hash 缓存）+ SKU→已发布标准版本绑定：优化方案评审稿（Phase0/Phase1）" DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`
  - 路线决策：先跑通“发货导入→SKU绑定→解析→BOM快照/异常→可重试/可重跑”，再扩展“模型套模型+自动编码”解决 30% 复杂产品
  - ERP口径补强清单：`DOC/costing/reviews/erp_guardrails_addendum_20251222.md`（版本为最小核算单元、重跑语义、编码定位、解析版本化、异常工作台、成本口径）
  - 验收命令：`grep -nF "ERP 口径补强清单（Guardrails Addendum）— 发货时再解析主链优先" DOC/costing/reviews/erp_guardrails_addendum_20251222.md`

- **本轮闭环产物（Frontend / 行级变体收口：ERP 最稳第一步）**：
  - 标准入口（`entryContext="standard"`）“清单编辑”Tab：物料行新增 **“变体（Overlay）”** 按钮
  - 点击按钮打开 `LineVariantDrawer`：管理 version-scoped `line-variants`（不修改基准清单）
  - Drawer 内支持 `spec_text` 预演：`POST /api/planner/spec/parse`（tokens） + `POST /api/planner/bom/generate`（最终 BOM + trace）
  - **收口（最稳形态）**：
    - action **固定** `replace_self`（UI 隐藏其它动作）
    - items **限制 1→1**（只允许 1 行目标物料，禁止新增第 2 行）
    - **同单位校验**：目标单位与基准行单位不一致 → 禁止启用并提示（单位缺失提示先补齐主数据/先保存清单）
    - **启用门槛**：启用前必须预演成功，并在 UI 显示最近预演时间/结果摘要（配置变更会标记“预演已过期”）
    - **条件增强（已接入 UI）**：在 token 基础上，额外支持 `width_between/height_between/area_between/perimeter_between`（可选）。若配置了这些条件，启用前要求预演样例能解析出对应数值（避免没测过就启用）。
    - **数量/个数条件（缺口）**：后端 `LineVariantCondition` 暂无 `quantity_between` 等字段；如业务必须支持“个数”，需要下一轮后端补字段或通过 token 离散化临时承载。

- **重要修复（Backend / 使 between 条件可落库）**：
  - 修复 `line-variants` 在写入 JSON 列时 `Decimal`/`tuple` 不可序列化导致 500：将 `conditions/metadata` 递归转为 JSON-safe（Decimal→字符串、tuple→list）。
  - 补齐缺失模块以恢复 `planner-costing.service` 可重启（恢复 `codes/processes/process_modules/product_models/product_model_versions` 路由与相关 service/utils）。

- **关键实现文件**：
  - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - `frontend/src/components/costing/LineVariantDrawer.tsx`
  - `frontend/src/services/planner.ts`
  - `frontend/src/types/planner.ts`
  - `frontend/src/pages/costing/ShipmentMonitorPage.tsx`
  - `frontend/src/pages/costing/SkuMasterWorkspacePage.tsx`
  - `frontend/src/pages/costing/ProcessModulesPage.tsx`
  - `backend/src/planner/routers/shipments.py`
  - `backend/src/planner/services/shipment_import_service.py`
  - `backend/src/planner/schemas.py`

- **本轮补充（Frontend / 模型清单：替换物料自动回填口径统一）**：
  - 问题：替换物料后，`unit_of_measure` / `metadata_json.bom_unit` / `calculation_method` / `bom_unit_price` 未同步更新，导致“计量方式与 BOM 单位不配套”、且表现为“所有行看起来都像同一种计量方式”。
  - 修复：
    - `ProductModelEditorDrawer` 在“替换物料”时强制同步回填：`unit_of_measure`、`metadata_json.bom_unit`、`calculation_method`，并尽量从主数据/换算推导 `bom_unit_price`。
    - `ProcessModulesPage` 在替换物料时不再沿用旧 `calculation_method`，改为以新物料主数据为准（避免回归）。
    - **补充（虚拟物料）**：替换虚拟物料时同样回填 `metadata_json.bom_unit_price`（优先用虚拟物料详情的 `bom_unit_price`；为空时按 bindings×真实物料 BOM 单价汇总推导），避免出现“VM00023 → VM00022 但 BOM 单价/单位不更新”。
  - 防回归：在关键函数旁加了“单位口径/计量方式必须匹配 normalizeUnit”的硬备注（禁止改回 `㎡/m` 作为 value）。
  - 本轮验收命令：`npm -C frontend run build`（已通过）

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮验收命令（必须）**：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Frontend / 只读：发货批次列表 + 异常队列 + BOM 快照查询）**：
  - 新增页面：`/costing/shipments`（只读）
  - 页面顶部新增：上传发货单（xlsx 导入）→ 调用 `POST /api/planner/shipments/import`，导入成功后自动选中 batch 并刷新列表/异常/快照
  - 页面包含 3 块：
    - 发货批次列表（分页，点击行设置当前 batch_id）
    - 异常队列（支持 batch_id/解决状态/limit 过滤）
    - BOM 快照查询（支持 batch_id/SKU/发货单号/spec_hash/limit 过滤，支持抽屉查看 trace + 最终 BOM 行摘要）
  - 依赖接口（后端已补齐最小查询能力）：
    - `GET /api/planner/shipments/import-batches?page=1&page_size=20`
    - `GET /api/planner/shipments/exceptions?batch_id=...&resolved=...&limit=...`
    - `GET /api/planner/shipments/bom-snapshots?batch_id=...&sku_code=...&shipment_no=...&spec_hash=...&limit=...`
  - 本轮验收命令（补充）：
    - Docs：`grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`
    - Backend smoke：`curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=1" | python -m json.tool`

- **本轮补充（Frontend / 替换物料选择器 MVP）**：
  - 位置：`LineVariantDrawer` 编辑弹窗的“替换物料”列
  - 行为：不再手输 `material_ref_id`；改为 **打开选择器 → 搜索（编码/名称）→ 选择**
  - 选择后回填：`material_ref_id + material_code/material_name/unit_of_measure`（用于可读展示 + 同单位校验）
  - 组件：新增 `frontend/src/components/costing/MaterialSelectModal.tsx`（复用 `/base-config/materials` 搜索接口，默认仅 BOM 物料）
- **本轮补充（Frontend / 变体规则录入体验收口）**：
  - `LineVariantDrawer` 的“编辑”弹窗改为 **多条规则表格**（同一触发类型下批量维护）：列为 启动/条件表达式/替换物料/β/α/覆盖率/损耗% + 新增/删除
  - 启用拦截：未预演成功或预演已过期时，不允许打开“启动”（前端直接提示）
  - 说明：当前版本仍按“同一触发类型”批量维护；若未来要允许每行触发类型不同，需要单独迭代 UI/保存/门槛（本轮暂停）

- **本轮补充（Backend / 缩略图恢复）**：
  - 恢复图片代理接口：`GET /api/planner/base-config/materials/{id}/images/{idx}`
  - 行为：优先读取 `metadata_json.local_images` 的本地文件；若缺失则从钉钉下载并落盘到 `PLANNER_MEDIA_DIR`，并回写 `metadata_json.local_images`
  - 纠偏：钉钉 `temporaryUrls` 在当前环境为 **GET** 且 `appType` 在路径里（非 POST）
  - 本地媒体目录默认：`backend/media`（已加入 `.gitignore`，避免误提交）

- **本轮补充（Backend / 行级变体 replace_self 用量兜底）**：
  - 修复历史规则“替换物料 β=0/计量方式默认 count”导致 `variant_item computed_quantity=0`
  - `bom/generate` 在 `replace_self` 下：若替换行未正确填写，则 **继承基准行的计量方式/β/单位**（避免用户必须重录旧规则）

- **下一步（不在本轮范围）**：
  - 若要允许“每行不同触发类型（token/宽/高/面积/周长混合）”并保持启用门槛正确：需要把触发类型下放到每行，并按行计算维度缺失/单位回填/预演样例覆盖
  - 如需更易用的物料选择（从物料/虚拟物料列表挑选并回填 material_ref_id），再开下一轮单独闭环。

- **下一步闭环任务单（运维/上线）**：`DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“行级变体（overlay）”到 47.99.89.206" DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **下一步闭环任务单（运维/上线：发货单导入→BOM快照）**：`DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“发货单导入→spec_cache→BOM快照”到 47.99.89.206（MVP）" DOC/agents/briefings/ops_deploy_shipment_import_bom_snapshots_to_4799.md`
- **下一步闭环任务单（运维/上线：前端发货单上传入口）**：`DOC/agents/briefings/ops_deploy_frontend_shipments_upload_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops 闭环任务单：部署前端“发货单上传导入入口”到 47.99.89.206（/costing/shipments）" DOC/agents/briefings/ops_deploy_frontend_shipments_upload_to_4799.md`
- **最新部署（2025-12-23 10:10 CST）**：
  - `47.99.89.206` 已执行 `git pull --ff-only`、`alembic upgrade heads`（存在 `0016_line_variants_mvp` 与 `0754ad7d6c3f` 双 head，采用 `heads` 选项同步）
  - `systemctl --user restart planner-costing.service`（需要 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`）后，`curl http://127.0.0.1:8800/api/planner/health` 返回 `{"status":"ok"}`
  - OpenAPI 校验：`/api/planner/shipments/import` / `/api/planner/shipments/exceptions` / `/api/planner/shipments/bom-snapshots` → `True`
  - 目标机验收：`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q` → `1 passed`
  - **本轮新增上线（SKU 主档工作台）**：
    - 后端：`alembic upgrade heads` 已运行 `0017 -> 0018_sku_master_import_mvp`，并重启 `planner-costing.service`
    - OpenAPI 校验：`/api/planner/sku-master` 与 `/api/planner/sku-master/import` → `True`
    - API 校验：`GET http://127.0.0.1:8800/api/planner/sku-master?page=1&page_size=10` → 200（`total=0, items=[]`）
    - 前端：静态资源已发布至 `/var/www/html/ai-costing/dist`

- **本轮闭环产物（Docs / 运营规范）**：`DOC/costing/manuals/standard_model_variants_ops_rules.md`（行级变体：token/尺寸边界/预演留痕/变更控制/扣库口径）
- **本轮验收命令（Docs）**：`grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`

- **接力准备（新 Frontend Agent）**：已刷新 `DOC/agents/handoff_frontend.md`，补齐行级变体 Overlay（`LineVariantDrawer`）与运营规范口径入口。

- **提炼件（禁止直读导出全文）**：`DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体收口：同单位 1→1 平替、规则上限、启用门槛等）
- **本轮验收命令（提炼件）**：`grep -nF "# 提炼：变体收口讨论（从 Cursor 导出记录提炼）" DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`

- **下一步闭环任务单（前端 UX 细化）**：`DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`（替换物料选择器：替代手输ID）
- **验收命令（派单文件存在）**：`grep -nF "# Frontend 闭环任务单：行级变体“替换物料”不再手输ID（选择器 + 自动回填 + 同单位校验）" DOC/agents/briefings/frontend_line_variants_material_picker_mvp.md`

- **下一步闭环任务单（SKU→库存扣料清单）**：`DOC/agents/briefings/backend_sku_binding_inventory_mvp.md`
- **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：SKU 绑定 + 规格解析尺寸/条件 + 生成库存扣料清单（BOM 快照）MVP" DOC/agents/briefings/backend_sku_binding_inventory_mvp.md`
- **下一步闭环任务单（发货单导入→BOM快照）**：`DOC/agents/briefings/backend_shipment_import_bom_snapshots_mvp.md`
- **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：发货单 Excel 导入 → spec_hash 缓存解析 → BOM 快照生成 + 异常队列（MVP）" DOC/agents/briefings/backend_shipment_import_bom_snapshots_mvp.md`
 - **下一步闭环任务单（SKU 主档导入/回写）**：`DOC/agents/briefings/backend_sku_master_import_and_autobind_mvp.md`
 - **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：SKU 主档导入（ERP 平台商品列表）+ 发货导入自动回写（MVP）" DOC/agents/briefings/backend_sku_master_import_and_autobind_mvp.md`
 - **下一步闭环任务单（前端 SKU 主档工作台）**：`DOC/agents/briefings/frontend_sku_master_workspace_mvp.md`
 - **验收命令（派单文件存在）**：`grep -nF "# Frontend 闭环任务单：SKU 主档工作台（导入/查询/命中率）MVP" DOC/agents/briefings/frontend_sku_master_workspace_mvp.md`

- **补充迭代（已完成）：SKU 主档“预解析缓存 + 规格差异标记”**：
  - 目标：在 SKU 主档中前置沉淀 `spec_hash/解析版本/尺寸/tokens/model_code_hint`，并在发货触发时记录“ERP规格 vs 最近发货规格”差异，避免重复解析、便于前端复核。
  - 前端展示：`/costing/sku-master` 列表显示 **对接状态 + 规格差异**，详情抽屉显示 `model_code_hint / erp_spec_hash / last_shipment_spec_text/hash / erp_dimensions/tokens`。
  - 后端实现：导入/回写时写入 `metadata_json`，并在 `GET /api/planner/sku-master` 列表/详情回传 computed 字段（避免前端 N+1）。
  - 验收命令：`pytest backend/tests/planner/test_sku_master_import_mvp.py -q && npm -C frontend run build`

- **方案产出（ERP回传工艺/生产规格）**：
  - `DOC/costing/blueprints/erp_writeback_process_spec_mvp.md`（把“可生产的工艺/规格 + 追溯ID”回写到ERP的最小口径/字段清单/幂等治理）
- **对外谈判资料（吉客云/ERP API需求表单）**：
  - `DOC/costing/blueprints/jky_api_requirements_form_v1.md`（一页式：读接口+写回接口+限流/幂等/字段字典要求）
  - `DOC/costing/blueprints/jky_after_sales_returns_requirements_form_v1.md`（售后/退货/作废/换货/补发：冲销与对账所需字段/接口/主键要求）

- **本轮闭环产物（Backend / 发货单导入→spec_hash缓存→BOM快照 + 异常队列 MVP）**：
  - 新增落库表：`shipment_import_batches`、`shipment_lines`、`spec_parse_snapshots`、`bom_snapshots`、`shipment_exception_queue`
  - 新增接口：
    - `POST /api/planner/shipments/import`（xlsx 导入→标准化→幂等→生成快照/入异常）
    - `GET /api/planner/shipments/import-batches/{batch_id}`
    - `GET /api/planner/shipments/exceptions?batch_id=...`
    - `GET /api/planner/shipments/bom-snapshots?batch_id=...`
  - 幂等口径：
    - 文件级：`file_hash=sha1(xlsx_bytes)`（同文件重复导入直接返回已成功 batch）
    - 行级：`external_line_key_hash=sha1(shipment_no|sku_code|spec_text|qty|revenue_amount)`（跨批次重复不重复生成 shipment_line/bom_snapshot）
  - 关键输出：`bom_snapshots.trace` 中回填 `bound_version_id + spec_hash + batch_id + shipment_line_id`
  - 本轮验收命令（必须）：`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q`

- **本轮闭环产物（Backend / SKU 主档导入 + 发货导入自动回写 MVP）**：
  - 新增落库表：`sku_master`（以 `erp_sku_barcode=货品条码（系统）` 为唯一键）
  - 新增接口：
    - `POST /api/planner/sku-master/import`（导入 `ERP 理 平台商品列表.xlsx` 过滤字段，按 barcode upsert）
    - `GET /api/planner/sku-master?search=&channel=&match_status=&page=&page_size=`
    - `GET /api/planner/sku-master/{id}`
  - 发货导入增强：`POST /api/planner/shipments/import` 若 barcode 未命中 `sku_master`，则创建最小主档（`metadata.source="shipment_autobackfill"`；不覆盖已存在主档）
  - 本轮验收命令（必须）：`pytest backend/tests/planner/test_sku_master_import_mvp.py -q`

- **本轮闭环产物（Frontend / SKU 主档工作台 MVP）**：
  - 新增页面：`/costing/sku-master`（成本核算菜单下新增入口：SKU 主档 / 商品关联）
  - 功能（MVP）：
    - 上传导入：调用 `POST /api/planner/sku-master/import`（xlsx + requested_by）
    - 列表分页：调用 `GET /api/planner/sku-master`（search/channel/match_status/page/page_size）
    - 详情抽屉：调用 `GET /api/planner/sku-master/{id}`（展示原始字段 + 图片预览 URL + metadata_json）

- **补充迭代（已完成）：SKU 主档绑定工作台（只选模型→唯一在线发布标准版本）**：
  - 手工绑定（不覆盖已有绑定）：
    - 右侧列表勾选 SKU 主档 → 左侧选择“已发布标准模型” → 一键绑定（自动落到该模型唯一 `published standard` 版本）
    - 后端接口：`GET /api/planner/sku-master/published-standard-models`、`POST /api/planner/sku-master/bind-by-model`
  - 自动绑定（确定性规则，带预览/执行）：
    - 仅对 `model_code_hint` 唯一命中“已发布标准模型”的未绑定 SKU 自动绑定
    - 后端接口：`POST /api/planner/sku-master/auto-bind/preview`、`POST /api/planner/sku-master/auto-bind/execute`
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：自动绑定预览→右侧候选列表→默认全选→仅绑定选中**：
  - 预览后：右侧列表自动切换为“命中候选视图”（只显示命中候选并默认全选），新增列展示匹配模型/命中词/命中方式
  - 执行：仅对“命中候选”中被勾选的记录执行绑定；未勾选则不绑定
  - 后端：`POST /api/planner/sku-master/auto-bind/execute` 支持 `sku_master_ids` 入参
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：标准模型“型号识别规则”（用于自动绑定识别）**：
  - 入口：标准模型编辑抽屉（`entryContext="standard"`）新增 Tab：**型号识别规则**
  - 规则：在模型 `metadata_json.recognition_keywords` 维护关键词（如 OZU：`丝圈地垫`、`丝圈`），用于从交易规格 `spec_text` 识别模型
  - 护栏：关键词在“已发布标准模型集合”内 **必须全局唯一**（保存时后端校验，避免歧义）
  - 自动链路：`sku-master auto-bind preview/execute` 优先按关键词命中模型，其次才用 `model_code_hint` 兜底
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_sku_master_binding_workbench_mvp.py -q`
    - Frontend：`npm -C frontend run build`

- **补充迭代（已完成）：型号识别规则 UI 列表化（新增/删除/校验/保存）**：
  - 交互：新增关键词→列表展示→可删除；提供“校验”按钮（不落库）与“保存”按钮（落库）
  - 后端：新增校验接口 `POST /api/planner/product-models/{id}/recognition/validate`
  - 验收命令：
    - Backend：`cd backend && . venv/bin/activate && pytest tests/planner/test_product_model_recognition_validate.py -q`
    - Frontend：`npm -C frontend run build`
    - 命中率/字段齐全（MVP）：在页面按“当前页”聚合展示
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮方案产物（SKU→BOM→发货/扣库/核算对账）**：`DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
- **本轮提炼件（发货单样例）**：`DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
- **本轮验收命令（提炼件/方案）**：
  - `grep -nF "# 提炼：发货单-理.xlsx（表头/前几行样例，基于xlsx-xml解析）" DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
  - `grep -nF "SKU 绑定 → 规格解析 → 动态 BOM → 发货/扣库/核算对账" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "external_line_key" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "交易规格（spec_text）变更" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
