## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-21 16:05（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
- **分支**：`backup/20251214-1535`
- **当前主任务（P0）**：把旧产品模型编辑器从 `frontend/src/pages/costing/CostingModelsPage.tsx` 迁移到 `frontend/src/components/costing/ProductModelEditorDrawer.tsx`，并接通两入口页。
- **上下文隔离硬约束**：
  - 打样入口 `/costing/sample-models`：只允许 sample 版本；只显示“生成标准模型”等打样侧动作
  - 标准入口 `/costing/standard-models`：只允许 standard 版本；显示“发布标准版本 / SKU 绑定 / 强制 1×1㎡口径”等标准侧动作；支持 `initialVersionId` 定位
- **后端接口已具备**：模型列表补齐版本统计字段；标准版本分页接口 `GET /api/planner/product-model-versions?...` 已存在并可用
- **验收标准（最小闭环）**：
  - 两个列表页打开抽屉后能加载版本/清单
  - 能保存版本清单（PUT version lines）
  - `npm -C frontend run build` 通过

- **已确认正确版本快照（请勿覆盖）**：
  - `DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.tsx`
  - 校验和：`DOC/index/extracted/ProductModelEditorDrawer_confirmed_20251221T042643Z.sha256`

- **本轮产物（单一闭环）**：新增 Hub Agent（新 Planner）派单 SOP/自检清单（可由用户每次贴给 Hub Agent 作为提醒），固化于 `DOC/agents/handoff_planner.md`
- **本轮验收命令**：`grep -n "Hub Agent（新 Planner）派单 SOP / 自检清单" DOC/agents/handoff_planner.md`

- **当前交付（P0.1 / 前端闭环）**：打样管理“清单编辑→计算汇总”区新增“推导标准模型”按钮（在“同步物料价格”前）；推导成功后可跳转到 `/costing/standard-models` 并自动打开对应标准版本抽屉；标准入口“标准版本TAB”改为表格（版本号/物料数/工序数/物料价/工序价/制造费/合计价/创建时间/操作）。
- **当前验收命令**：`npm -C frontend run build`

- **当前主任务（P0.2 / 方案闭环）**：输出“标准模型：变体/动态 BOM 功能方案”（SKU 绑定→规格解析→**行级变体（每行变体图标 + 变体物料清单表）**→最终BOM），见 `DOC/costing/blueprints/standard_model_variants_plan.md`
- **当前验收命令（方案）**：`grep -n "^# 标准模型：变体 / 动态 BOM 功能方案" DOC/costing/blueprints/standard_model_variants_plan.md`

- **方案关键确认（交互）**：点击物料行“变体”按钮 → 弹出独立面板管理“变体清单（overlay）”；**基准标准清单不直接修改**（变体用于动态生成/预览/订单出料）。

- **下一步闭环任务单（后端）**：`DOC/agents/briefings/backend_line_variants_mvp.md`（行级变体 overlay + spec/parse tokens + bom/generate MVP；ADD 挂锚点行）
- **验收命令（派单文件存在）**：`grep -nF "# Backend 闭环任务单：行级变体（overlay）+ 规格解析（tokens）MVP" DOC/agents/briefings/backend_line_variants_mvp.md`

- **下一步闭环任务单（前端）**：`DOC/agents/briefings/frontend_line_variants_panel_mvp.md`（物料行“变体”按钮 + Overlay Drawer（不改基准清单）+ 预演对接 spec/parse & bom/generate）
- **验收命令（派单文件存在）**：`grep -nF "# Frontend 闭环任务单：物料行“变体”按钮 + Overlay Drawer（接后端 line-variants/spec/parse/bom）" DOC/agents/briefings/frontend_line_variants_panel_mvp.md`

- **当前交付（方法论复用）**：新增跨项目可复用的“Hub Agent 派单体系标准说明”，见 `DOC/agents/task_distribution_standard.md`
- **验收命令（方法论文档存在）**：`grep -nF "# Hub Agent 派单体系：跨项目标准说明（可复用）" DOC/agents/task_distribution_standard.md`
- **本轮产物（Backend 行级变体 MVP）**：落库 `product_model_line_variants` + `product_model_line_variant_items` 表，新增 `Spec Parser`、`Line Variants`、`BOM Generate` 三类服务（FastAPI 路由 + Service + Alembic），行级变体允许 version-scoped 绑定、整组替换/删除/追加，`spec/parse` 输出 tokens + 尺寸 +解释，`bom/generate` 依据锚点/优先级套用 overlay 并返回 trace。README/Task Log/State 已同步说明。补充修复：审计日志 payload 现支持 Decimal/日期/UUID 序列化，变体 items 保存时自动回填引用物料编码/名称/单位/计量方式，确保 BOM 结果字段齐全。
- **后端验收命令**：`pytest backend/tests/planner/test_line_variants_mvp.py -q`
- **前端验收命令**：`npm -C frontend run build`
- **下一步提醒**：1）前端接入行级变体面板 + 动态 BOM 预览；2）按派单要求将代码部署到 47.99.89.206（git pull → alembic upgrade head → systemctl restart → `curl http://47.99.89.206:8800/openapi.json` 确认 `/api/planner/processes` 与新接口可见）；3）若需读取更多文档，请先更新 `DOC/agents/workset.md`。
