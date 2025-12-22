## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-22 22:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
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
  - `backend/src/planner/routers/shipments.py`
  - `backend/src/planner/services/shipment_import_service.py`
  - `backend/src/planner/schemas.py`

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
- **最新部署（2025-12-22 21:10 CST）**：
  - `47.99.89.206` 已执行 `git pull --ff-only`、`alembic upgrade heads`（存在 `0016_line_variants_mvp` 与 `0754ad7d6c3f` 双 head，采用 `heads` 选项同步）
  - `systemctl --user restart planner-costing.service`（需要 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`）后，`curl http://127.0.0.1:8800/api/planner/health` 返回 `{"status":"ok"}`
  - OpenAPI 校验：`/api/planner/shipments/import` / `/api/planner/shipments/exceptions` / `/api/planner/shipments/bom-snapshots` → `True`
  - 目标机验收：`pytest backend/tests/planner/test_shipment_import_bom_snapshots_mvp.py -q` → `1 passed`

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

- **本轮方案产物（SKU→BOM→发货/扣库/核算对账）**：`DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
- **本轮提炼件（发货单样例）**：`DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
- **本轮验收命令（提炼件/方案）**：
  - `grep -nF "# 提炼：发货单-理.xlsx（表头/前几行样例，基于xlsx-xml解析）" DOC/index/extracted/shipment_xlsx_extracted_20251222T000000+0800.md`
  - `grep -nF "SKU 绑定 → 规格解析 → 动态 BOM → 发货/扣库/核算对账" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "external_line_key" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
  - `grep -nF "交易规格（spec_text）变更" DOC/costing/blueprints/sku_binding_bom_shipment_plan.md`
