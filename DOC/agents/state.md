## 当前状态（崩了也能继续）

- **最近校对（北京时间 GMT+8）**：2025-12-21（接力入口：`DOC/agents/handoff_planner.md` / `DOC/agents/handoff_frontend.md`）
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



