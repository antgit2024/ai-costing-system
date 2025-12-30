## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-30 19:20（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_backend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-30 19:47（Frontend Agent：真实物料详情“引用关系区块”MVP 已接入并验收）

- **最近校对（北京时间 GMT+8）**：2025-12-25 04:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 06:08（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 14:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 16:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-25 17:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-26 10:20（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **最近校对（北京时间 GMT+8）**：2025-12-30 12:30（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_backend.md`）
- **分支**：`backup/20251214-1535`

- **本轮闭环产物（Frontend / 接力恢复包 + 强制验收）**：
  - 更新接力包：`DOC/agents/handoff_frontend.md` 刷新“最近校对”时间戳（用于新 Frontend 接力入口）
  - 硬验收（全部 0 退出码）：
    - `cd frontend && npm ci`
    - `npm -C frontend run build`
    - Docs：按 `DOC/agents/commands.md` 的 4 条 `grep -nF ...` 校验文档存在性
    - Backend smoke：`curl -sS "http://127.0.0.1:8800/api/planner/product-model-versions?version_kind=standard&page=1&page_size=20" | python -m json.tool`
  - 下一步（Frontend 建议闭环）：
    - 按 `DOC/agents/state.md` 既有规划，在“停用/删除/改单位/改换算/改单价”等高风险操作前调用 `GET /api/planner/base-config/materials/{material_id}/references` 做影响范围提示与确认/拦截

- **本轮闭环产物（Frontend / Materials - MaterialReferencesPanel（真实物料详情：引用关系区块 MVP））**：
  - UI：`/costing/materials` 物料详情抽屉新增 Tab：**“引用”**，展示三类引用（均为 `count + 最近10条`）并提供跳转入口：
    - 虚拟物料绑定引用 → `/costing/virtual-materials`
    - 工艺模块引用 → `/costing/process-modules`
    - 模型版本清单引用 → `/costing/standard-models`
  - 性能收口：仅在“抽屉打开且 material_id 已知”时请求一次（不在列表页做 N+1 预取）
  - Fail-open：请求失败或 `errors[]` 非空时，仅在引用区块提示“部分数据不可用”，不阻塞其它功能
  - 关键改动文件：
    - `frontend/src/services/planner.ts`（新增 `fetchMaterialReferences`）
    - `frontend/src/types/planner.ts`（新增 `MaterialReferencesResponse` 等类型）
    - `frontend/src/pages/costing/MaterialMasterPage.tsx`（新增“引用”Tab）
  - 本轮验收命令（必须）：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Backend / BaseConfig - MaterialReferences（真实物料引用关系查询 MVP））**：
  - 新增接口：`GET /api/planner/base-config/materials/{material_id}/references`
  - 返回结构要点：
    - `material_id`
    - `virtual_materials.count/items`（最近 10 条，含 `id/virtual_code/name/virtual_kind/status`）
    - `process_modules.count/items`（最近 10 条，含 `id/name`）
    - `product_model_versions.count/items`（最近 10 条，含 `version_id/model_id/model_name/version_label/version_kind/version_status`）
    - `errors[]`：任一引用源查询失败时，接口仍返回 200，但该块返回空并记录错误（用于前端高风险操作前的影响评估）
  - 性能收口：仅返回“计数 + 最近 N 条”（N=10），不返回大 payload
  - 验收命令：
    - `curl -sS "http://127.0.0.1:8800/api/planner/base-config/materials/<material_id>/references" | python -m json.tool`
  - 下一步（前端）：
    - 在“停用/删除/改单位/改换算/改单价”等高风险操作前调用该接口，展示影响范围并做确认/拦截

- **本轮闭环产物（Backend / 修复 Task Center 500：Postgres SSL）**：
  - 现象：前端 `GET /api/planner/task-center/recent?limit=5` 轮询报 500
  - 根因：环境链路对 Postgres SSL 协商支持不一致（可能出现 `no encryption` 或 `server does not support SSL`），需要用 `sslmode` 明确策略
  - 修复：
    - `backend/src/database.py`：Postgres URL 默认补齐 `sslmode=prefer`；若设置 `PLANNER_PG_SSLMODE` 则强制覆盖 URL 内 sslmode
    - `backend/src/planner/routers/jobs.py`：task-center 查询失败时 fail-open（避免角标轮询拖垮页面）
  - 当前阻塞（重要）：若 **Postgres 未续费/不可用**（或链路被替换成不支持 SSL 的实例），则依赖 DB 的页面接口仍会 500（例如 `/api/planner/processes`、`/api/planner/taxonomy/items`）；task-center 之所以能 200 是因为做了 fail-open。
  - 验收命令：
    - `curl -sS -D - "http://127.0.0.1:8800/api/planner/task-center/recent?limit=5" -o /tmp/task_center_recent.json && cat /tmp/task_center_recent.json`

- **本轮闭环产物（Planner-Optimization / 方案评审稿）**：
  - `DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`（回答：SKU_NOT_BOUND 根因与治理、spec_hash+解析版本化、幂等与重试/重跑语义、UI按Excel展示）
  - 验收命令：`grep -nF "发货时再解析（spec_hash 缓存）+ SKU→已发布标准版本绑定：优化方案评审稿（Phase0/Phase1）" DOC/costing/reviews/shipment_time_parse_review_phase0_phase1_20251222.md`
  - 路线决策：先跑通“发货导入→SKU绑定→解析→BOM快照/异常→可重试/可重跑”，再扩展“模型套模型+自动编码”解决 30% 复杂产品
  - ERP口径补强清单：`DOC/costing/reviews/erp_guardrails_addendum_20251222.md`（版本为最小核算单元、重跑语义、编码定位、解析版本化、异常工作台、成本口径）
  - 验收命令：`grep -nF "ERP 口径补强清单（Guardrails Addendum）— 发货时再解析主链优先" DOC/costing/reviews/erp_guardrails_addendum_20251222.md`
  - VM策略：已在 ERP Guardrails 增补页 §8 固化（推荐混合模式：VM用于表达/复用，发货/扣库必须展开到真实物料并落快照；绑定变更不回写历史快照）
  - 主数据不同频策略：已在 ERP Guardrails 增补页 §9 固化（宜搭同步物料↔本地模型引用：唯一键/选择器防错/发布校验/健康检查/去重归并）

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

- **本轮闭环产物（Frontend / 打样管理：清单编辑 UI 修复）**：
  - 位置：`/costing/sample-models` → 打开抽屉 → `清单编辑`
  - 修复点：
    - 工序组“计量方式”右侧圆感叹号 tooltip：文本改为白色（深色 tooltip 背景可读）
    - 新增物料/新增工序：手动新增的行统一灰底（不再使用彩色模块背景）
    - 工序组列收口：将“替换”列更名为“操作”，并把 `α`（调参面板）按钮移入“操作”列与“替换”合并（宽度与物料组操作列一致）
    - 避免“打开抽屉/切版本”时尺寸联动重算覆盖已保存的本品用量/用时：仅当用户实际修改尺寸输入框时才触发联动重算
  - 关键文件：`frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - 本轮验收命令：`npm -C frontend run build`（已通过）

- **本轮闭环产物（Standard Models / 标准版本 → 克隆为新标准模型）**：
  - 需求：在“标准模型管理 → 标准版本”中，从某个标准版本生成一个**全新的标准模型**（新编码 + 新版本号），用于大量相似型号的快速复用
  - 前端：
    - 标准版本列表：将“复制”更名为“复制版”，并新增按钮“克隆模型”
    - 点击“克隆模型”：调用后端 `POST /api/planner/product-model-versions/{version_id}/clone-model`，成功后跳转到 `/costing/standard-models` 自动打开新模型抽屉并定位新标准版本
  - 后端：
    - 新接口：`POST /api/planner/product-model-versions/{version_id}/clone-model`
    - 行为：从源 standard version 克隆出新 ProductModel（model_code 自动生成）+ 新 standard draft version（version_label 自动生成）+ 复制版本清单；可选复制 line-variants（overlay）并按行序映射 base_line_id
  - 关键文件：
    - `backend/src/planner/routers/product_model_versions.py`
    - `backend/src/planner/schemas.py`
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
    - `frontend/src/services/planner.ts`
    - `frontend/src/types/planner.ts`
  - 验收命令：
    - Backend：`./backend/venv/bin/python -m pytest backend/tests/planner/test_clone_model_from_standard_version.py -q`
    - Frontend：`npm -C frontend run build`

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

- **本轮闭环产物（BOM 成本展示 + 工序明细 + 历史快照回填）**：
  - 动态 BOM 成本口径：
    - `POST /api/planner/bom/generate` 返回每条物料行 `bom_unit_price/line_cost`
    - `trace.costing` 返回 `material_cost_total/process_cost_total/overhead_cost(默认30%)/total_cost/unit_cost`
    - 并补充 `trace.costing.process_lines`（工序明细，含计价参数/行成本/警告）
  - 发货监控页（`/costing/shipments`）抽屉重构：
    - 解析队列 BOM 预览抽屉、BOM 快照详情抽屉统一为 Tabs：汇总 / 物料 / 工序 / Trace
  - 新增“历史快照回填”：
    - 后端：`POST /api/planner/shipments/bom-snapshots/{snapshot_id}/recompute`
    - 前端：BOM 快照列表新增“回填”按钮（回填后刷新并打开详情）

- **盘点/扣库模式确认（待后续实现）**：
  - 当前业务走“发货触发标准回冲（Backflush）按 BOM 标准比例扣真实物料”，月底盘点对真实物料做差异调整；虚拟物料不作为盘点库存对象。

- **本轮补充（扣库清单：虚拟物料→真实物料展开）**：
  - 背景：BOM 快照/预览的“物料”表可能主要是虚拟物料（VM），但库存扣减必须落在真实物料（Material）。
  - 实现：`POST /api/planner/bom/generate` 的 `trace.inventory.inventory_lines` 返回“真实物料扣库清单”（把 virtual 行按 `virtual_material_bindings` 展开并聚合）。
  - 前端：`/costing/shipments` 的 BOM 预览抽屉 / 快照详情抽屉新增 Tab：**扣库清单（真实物料）**，用于对账与后续扣库/盘点闭环。
  - 提示：历史快照若缺失该字段，可用“回填”重算后补齐。

- **下一阶段（真实数据实测 + UI 整理规划）**：
  - 线上直接跑：`47.99.89.206`
  - 首批真实文件：由业务侧上传（平台商品列表 / 发货单）
  - 目标覆盖：约 200 行
  - 成本口径阶段性固定：物料 + 工序 + 制造费 30%
  - 验收清单（可勾选）：`DOC/costing/manuals/real_data_uat_checklist_20251225.md`

- **本轮补充（确定性工艺余量：扎口/封边等固定长度）**：
  - 背景：宽度不固定，但扎口固定（例如两边各 +10cm），属于“确定性尺寸修正”，不应使用损耗%硬凑。
  - 后端：BOM 计算支持物料行 `metadata_json.extra_width_mm/extra_height_mm`（单位mm），计量时使用 `(width_mm+extra_width_mm, height_mm+extra_height_mm)`。
  - 前端：标准模型清单物料行增加列 **工艺余量(mm)**（+宽 / +高），录入后会联动重算本品用量/标准用量。

- **本轮补充（计量方式扩展：长边/短边，单位=米）**：
  - 背景：编织袋/包装类材料存在“宽度不固定，但用料沿长边/短边卷”的口径；仅靠 width/height 无法表达“取最长边/最短边”。
  - 后端：`_measure_qty` 新增 `long_side/short_side`（分别取 `max(width,height)` / `min(width,height)`，并乘以数量）。
  - 前端：
    - 物料详情（`/costing/materials`）“计算方式”支持 **长边/短边**，并校验其 BOM 单位只能为“米”。
    - 模型清单“计量方式”下拉补充 **长边/短边**（仅单位=米时允许选择）。

- **本轮验收命令（必须）**：
  - Frontend：`npm -C frontend run build`
  - Backend（快速 smoke）：`curl -sS "http://127.0.0.1:8800/api/planner/shipments/bom-snapshots?limit=1" | python -m json.tool`
  - Backfill API（示例）：`curl -sS -X POST "http://127.0.0.1:8800/api/planner/shipments/bom-snapshots/<snapshot_id>/recompute" -H "Content-Type: application/json" -d '{"operator_id":"planner_user"}' | python -m json.tool`

- **本轮补充（Frontend / 模型清单：替换物料自动回填口径统一）**：
  - 问题：替换物料后，`unit_of_measure` / `metadata_json.bom_unit` / `calculation_method` / `bom_unit_price` 未同步更新，导致“计量方式与 BOM 单位不配套”、且表现为“所有行看起来都像同一种计量方式”。
  - 修复：
    - `ProductModelEditorDrawer` 在“替换物料”时强制同步回填：`unit_of_measure`、`metadata_json.bom_unit`、`calculation_method`，并尽量从主数据/换算推导 `bom_unit_price`。
    - `ProcessModulesPage` 在替换物料时不再沿用旧 `calculation_method`，改为以新物料主数据为准（避免回归）。
    - **补充（虚拟物料）**：替换虚拟物料时同样回填 `metadata_json.bom_unit_price`（优先用虚拟物料详情的 `bom_unit_price`；为空时按 bindings×真实物料 BOM 单价汇总推导），避免出现“VM00023 → VM00022 但 BOM 单价/单位不更新”。
  - 防回归：在关键函数旁加了“单位口径/计量方式必须匹配 normalizeUnit”的硬备注（禁止改回 `㎡/m` 作为 value）。
  - 本轮验收命令：`npm -C frontend run build`（已通过）

- **本轮补充（Materials / 宜搭同步分模式 + 前端按钮拆分）**：
  - 背景：物料页原“同步宜搭”属于全量 upsert，用户需要更安全/更快的同步方式（只拉新、只更新价格关键字段）。
  - 后端：`POST /api/planner/base-config/materials/sync-yida` 新增 `mode`：
    - `full`：全量同步（默认，raw_form_data 全量覆盖）
    - `new_only`：仅新增新物料（已存在的不更新）
    - `core_fields`：仅更新关键字段（入库单价/单位、采购单价/单位、采购→入库换算、采购规格），并且 raw_form_data 只 merge 对应字段
  - 前端：`/costing/materials` 顶部按钮拆分为 **同步新物料 / 更新原价格 / 全量同步宜搭**（均会打开同步日志抽屉便于跟踪）
  - 新增“推导BOM价格”：
    - 入口：`/costing/materials` 刷新按钮右侧
    - 后端接口：`POST /api/planner/base-config/materials/derive-bom-prices`（后台任务，写入 `metadata_json.bom_unit_price`）
    - 推导口径：\(BOM单价 = 入库单价 \div 入库→BOM换算\)，用于算价/扣库；无法推导时列表以红字提示原因
    - 自动化：三种宜搭同步任务完成后会自动触发一次 BOM 价格推导
  - 本轮验收命令：`npm -C frontend run build`（已通过）；Backend smoke：用 curl 触发 `mode=new_only/core_fields` 与 `derive-bom-prices` 均可成功落库

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮验收命令（必须）**：`npm -C frontend run build`（已通过）

---

- **本轮闭环产物（Virtual Materials / 虚拟物料列表&抽屉体验 + 分类治理）**：
  - 前端：`/costing/virtual-materials`
    - 列表默认展示“子物料逐行明细”（编码/名称/配比或每套数量/损耗率）
    - 操作列对齐工序管理：图标化按钮（启用/停用/删除归档等，带安全约束与二次确认）
    - 筛选增强：类型（占位/配方/套件）+ 绑定物料搜索（按子物料编码/名称）
    - 分类来源：虚拟物料分类使用 taxonomy `virtual_material_category`
    - “同步数据”增强：同步后提示哪些子物料 BOM 单价缺失/为 0，避免误判“没更新”
  - 后端：
    - `GET /api/planner/base-config/virtual-materials` 新增筛选参数：
      - `virtual_kind`（占位/配方/套件）
      - `binding_search`（按绑定子物料编码/名称过滤）
  - 关键文件：
    - `frontend/src/pages/costing/VirtualMaterialsPage.tsx`
    - `frontend/src/types/planner.ts`
    - `backend/src/planner/routers/base_config.py`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `python -m compileall backend/src/planner/routers/base_config.py`
  - 最近校对（北京时间 GMT+8）：2025-12-28

---

- **本轮闭环产物（Pickers / 统一“添加物料/添加工序”弹窗体验）**：
  - 目标：统一虚拟物料/工艺模块的“添加物料/选择工序”弹窗交互，减少各页各造一套导致的不一致与学习成本。
  - 前端：
    - `frontend/src/components/costing/MaterialPickerDrawer.tsx`：统一物料选择器 Drawer
      - 顶部 Tabs：真实物料 / 虚拟物料
      - 真实物料筛选区：关键词 + 分类（taxonomy `material_category`）+ **默认勾选“仅 BOM 物料”**
      - 虚拟物料筛选区：关键词 + 分类（taxonomy `virtual_material_category`）
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`：
      - 物料选择入口不再走“二级选择（真实/BOM/虚拟）”，统一打开 `MaterialPickerDrawer`
      - 选择工序弹窗新增“分类”筛选（taxonomy `process_category`）
  - 后端：
    - `GET /api/planner/processes/references` 支持 `category` 过滤（与主列表一致），用于前端工序选择器。
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `python -m compileall backend/src/planner/routers/processes.py`
  - 最近校对（北京时间 GMT+8）：2025-12-28

- **本轮闭环产物（Frontend / 工艺模块列表页：对齐“工序管理”两行风格 + 操作图标化）**：
  - 目标：让“工艺模块”列表可扫读（两行信息密度）并与“工序管理”视觉一致。
  - 变更点：
    - 列表列改造（`ProcessModulesPage`）：
      - “工艺模块”列：第一行名称（加粗）；第二行显示 `分类/版本/引用次数` + 胶囊标签（最多 3 个，超出显示 +N）
      - “描述”列：两行省略（ellipsis rows=2 + tooltip）
      - “操作”列：图标按钮（带边框 + Tooltip）→ 查看/编辑/AI/复制/启用/停用
  - 关键文件：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
    - `frontend/src/guides/table_list_style_two_line_cells.md`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF \"title: '描述'\" frontend/src/pages/costing/ProcessModulesPage.tsx`
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:10

- **本轮闭环产物（Frontend / Chrome“页面无响应”卡死：任务角标轮询降载）**：
  - 现象：页面内交互（悬停 Tooltip/点击）都卡住，Chrome 弹“页面无响应”。这通常是前端主线程被长任务占满。
  - 根因假设（高概率）：`AppLayout` 顶部任务角标在后台轮询 `task-center`，返回 payload/result 可能很大；有运行中任务时频率更高，导致频繁 JSON 解析与 React 更新，拖死主线程。
  - 修复（最小）：`frontend/src/components/layout/AppLayout.tsx`
    - 探针请求 `limit` 从 30 降到 5
    - `select` 将缓存数据压缩为 `{statuses, runningCount}`（不保留大 payload）
    - 页面不可见时停止轮询（`document.visibilityState==='hidden'`）
    - 轮询频率降低：运行中 5s / 空闲 15s；并关闭 `refetchOnWindowFocus`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF \"任务角标探针（性能敏感）\" frontend/src/components/layout/AppLayout.tsx`
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:25

- **本轮闭环产物（Ops-ish / 彻底解决：静态资源原子发布，避免 chunk 404→HTML 回退导致白屏/卡死）**：
  - 现象：前端报 `Failed to load module script (MIME text/html)` / `Failed to fetch dynamically imported module`，页面随即白屏或“点不了/无响应”。
  - 根因：静态资源发布非原子 +（或）Nginx 对 `/assets/*` 发生错误回退，导致 chunk 丢失却返回 HTML。
  - 修复：
    - `frontend/scripts/deploy_static.sh` 改为**原子发布**：同步到临时目录 → 一次性 `mv` 切换，避免线上半发布状态。
    - `DOC/agents/known_issues.md` 补充“Failed to load module script（MIME text/html）”的根因与 Nginx 必要配置。
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `bash -n frontend/scripts/deploy_static.sh`
    - `grep -nF \"原子发布\" frontend/scripts/deploy_static.sh`
  - 下一步（需要有权限的人做）：按 `DOC/agents/known_issues.md` 调整 Nginx 的 `/assets` try_files 与缓存头。
  - 最近校对（北京时间 GMT+8）：2025-12-27 18:40

- **本轮闭环产物（Frontend / RESULT_CODE_HUNG：移除 render 内自动纠偏导致的渲染循环）**：
  - 现象：Chrome 报 `RESULT_CODE_HUNG`，页面鼠标悬停/点击都卡住。
  - 根因假设（高概率）：在表格单元格 `render` 过程中触发 `queueMicrotask()+setFieldValue/setState`，导致渲染-微任务-渲染循环，最终主线程被占满。
  - 修复（最小）：
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`：移除 render 内 `queueMicrotask()+form.setFieldValue` 的自动纠偏；改为保存时规范化 `calculation_method/measure_unit`。
    - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`：移除 render 内 `queueMicrotask()+setMaterials` 的自动纠偏；保存清单前统一规范化非法 `calculation_method` 并重算用量。
  - 本轮验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:05

- **本轮闭环产物（Process Modules / 列表删除（归档））**：
  - 需求：工艺模块列表增加“删除”功能（归档删除），与工序管理一致。
  - 后端：
    - 新增：`DELETE /api/planner/process-modules/{module_id}`（204）
    - 口径：启用中不可删；若仍被模型引用（`model_process_modules`）则阻止删除并提示引用数。
  - 前端：
    - `ProcessModulesPage` 操作列新增“删除”图标按钮（仅非 active 显示，带二次确认）
    - `frontend/src/services/planner.ts` 新增 `deleteProcessModule()`
  - 验收命令：
    - `npm -C frontend run build`
    - `grep -n \"@router.delete\" backend/src/planner/routers/process_modules.py`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:25

- **本轮闭环产物（Processes / 列表删除按钮可见性增强）**：
  - 反馈：工序管理列表“删除功能看不到”。
  - 说明：后端删除口径要求先停用（active 不允许删除）。
  - 前端改造：`frontend/src/pages/costing/ProcessesPage.tsx`
    - 删除按钮**始终显示**；当工序为 active 时，“删除”按钮置灰并提示“需先停用”。
  - 验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 19:45

- **本轮闭环产物（Standard Models / “直接新建标准（高级）”误报失败修复）**：
  - 现象：点击“直接新建标准（高级）”创建成功（模型已生成），但 UI 仍提示“新建标准模型失败”。
  - 根因：创建成功后，后续步骤（取 `current_draft_version_id` / 列表 refetch）任一异常会被 catch，当成创建失败误报。
  - 修复：`frontend/src/pages/costing/StandardModelsPage.tsx`
    - `current_draft_version_id` 读取兼容 `metadata_json` / `metadata`
    - 若未返回 draft id：兜底 `fetchProductModelVersions(model.id)` 自动选取 standard draft
    - 列表 `refetch` 失败不再覆盖“创建成功”反馈（改为忽略）
  - 验收命令：
    - `npm -C frontend run build`
  - 最近校对（北京时间 GMT+8）：2025-12-27 20:05

- **本轮闭环产物（Frontend / 工艺模块 AI 语义抽屉重构：自动汇总为主、步骤级补丁、手工不覆盖）**：
  - 目标：让员工看懂“这个工艺模块怎么做”，并让模块级 AI 字段主要来自工序库 ai_spec 自动汇总，避免重复手填。
  - 变更点：
    - `AI 语义（工艺模块）` 抽屉新增按钮：
      - “从工序自动汇总（只填空）”：按模块已选工序拉取工序库 `metadata_json.ai_spec`，汇总到模块级字段，仅填空。
      - “从工序自动汇总（覆盖）”：覆盖未锁定字段（不会覆盖手工锁定字段）。
    - 新增手工锁定：保存时把人工编辑过的字段写入 `metadata_json.ai_spec._manual_overrides`，后续汇总默认不覆盖。
    - 步骤级区块增加解释文案，并把按钮文案改为“引用工序AI→步骤”（步骤级用于少量差异化补丁）。
  - 关键文件：
    - `frontend/src/components/costing/ProcessModuleAIDrawer.tsx`
    - `frontend/src/pages/costing/ProcessModulesPage.tsx`
  - 本轮验收命令：
    - `npm -C frontend run build`
    - `grep -nF "从工序自动汇总（只填空）" frontend/src/components/costing/ProcessModuleAIDrawer.tsx`
  - 下一步（可选，不在本轮范围）：对“AI生成写入 narrative_long”加“手工锁定字段覆盖确认”提示（尊重 `_manual_overrides.narrative_long`）。
  - 最近校对（北京时间 GMT+8）：2025-12-27 17:30

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
