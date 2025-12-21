## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-21 22:40（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **分支**：`backup/20251214-1535`

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

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮验收命令（必须）**：`npm -C frontend run build`（已通过）
- **本轮补充（Frontend / 变体规则录入体验收口）**：
  - `LineVariantDrawer` 的“编辑”弹窗改为 **多条规则表格**（同一触发类型下批量维护）：列为 启动/条件表达式/替换物料/β/α/覆盖率/损耗% + 新增/删除
  - 启用拦截：未预演成功或预演已过期时，不允许打开“启动”（前端直接提示）
  - 说明：当前版本仍按“同一触发类型”批量维护；若未来要允许每行触发类型不同，需要单独迭代 UI/保存/门槛（本轮暂停）

- **下一步（不在本轮范围）**：
  - 若要允许“每行不同触发类型（token/宽/高/面积/周长混合）”并保持启用门槛正确：需要把触发类型下放到每行，并按行计算维度缺失/单位回填/预演样例覆盖
  - 如需更易用的物料选择（从物料/虚拟物料列表挑选并回填 material_ref_id），再开下一轮单独闭环。

- **下一步闭环任务单（运维/上线）**：`DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“行级变体（overlay）”到 47.99.89.206" DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **最新部署（2025-12-21 20:10 CST）**：
  - `47.99.89.206` 已执行 `git pull --ff-only`、`alembic upgrade heads`（存在 `0016_line_variants_mvp` 与 `0754ad7d6c3f` 双 head，采用 `heads` 选项同步）
  - `systemctl --user restart planner-costing.service` 后，`curl http://127.0.0.1:8800/api/planner/health` 返回 `{"status":"ok"}`
  - 前端 `npm -C frontend ci && npm -C frontend run build`，并通过 `PLANNER_STATIC_DIR=/var/www/html/ai-costing/dist ./scripts/deploy_static.sh` 发布
  - 验收命令：`curl -sS http://127.0.0.1:8800/openapi.json | python -c "... print(...)"` → `True`（确认 `spec/parse` / `bom/generate` / `line-variants` 路由已生效）

- **本轮闭环产物（Docs / 运营规范）**：`DOC/costing/manuals/standard_model_variants_ops_rules.md`（行级变体：token/尺寸边界/预演留痕/变更控制/扣库口径）
- **本轮验收命令（Docs）**：`grep -nF "## 标准模型：行级变体（Overlay）运营/实施规范（v0.1）" DOC/costing/manuals/standard_model_variants_ops_rules.md`

- **接力准备（新 Frontend Agent）**：已刷新 `DOC/agents/handoff_frontend.md`，补齐行级变体 Overlay（`LineVariantDrawer`）与运营规范口径入口。

- **提炼件（禁止直读导出全文）**：`DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`（变体收口：同单位 1→1 平替、规则上限、启用门槛等）
- **本轮验收命令（提炼件）**：`grep -nF "# 提炼：变体收口讨论（从 Cursor 导出记录提炼）" DOC/index/extracted/variants_discussion_extracted_20251221T200250+0800.md`
