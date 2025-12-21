## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-21 16:20（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **分支**：`backup/20251214-1535`

- **本轮闭环产物（Frontend / 行级变体 UI MVP）**：
  - 标准入口（`entryContext="standard"`）“清单编辑”Tab：物料行新增 **“变体（Overlay）”** 按钮
  - 点击按钮打开 `LineVariantDrawer`：管理 version-scoped `line-variants`（不修改基准清单）
  - Drawer 内支持 `spec_text` 预演：`POST /api/planner/spec/parse`（tokens） + `POST /api/planner/bom/generate`（最终 BOM + trace）

- **关键实现文件**：
  - `frontend/src/components/costing/ProductModelEditorDrawer.tsx`
  - `frontend/src/components/costing/LineVariantDrawer.tsx`
  - `frontend/src/services/planner.ts`
  - `frontend/src/types/planner.ts`

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮验收命令（必须）**：`npm -C frontend run build`（已通过）

- **下一步（不在本轮范围）**：如需更易用的 items 选材（从物料/虚拟物料列表挑选并回填 material_ref_id），再开下一轮单独闭环。

- **下一步闭环任务单（运维/上线）**：`DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
- **验收命令（派单文件存在）**：`grep -nF "# Ops/Backend Ops 闭环任务单：部署“行级变体（overlay）”到 47.99.89.206" DOC/agents/briefings/ops_deploy_line_variants_to_4799.md`
