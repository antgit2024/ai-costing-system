# Frontend Phase 0/1 Planner Brief

## 目标
- 在 `feature/costing-frontend` 分支实装 Planner 前端工作区骨架。
- 与后端 `/api/planner/*` 模块对接，完成 initiative / package / line-item 三大视图及 CSV 导入入口。
- 提供 Scenario Builder 占位页面，保留交互按钮，为 Phase 2 场景快照能力铺垫。

## 交付清单
1. **全局框架**
   - 新建 React + Vite + Ant Design 前端（TypeScript）。
   - 提供 `/planner` 主路由和 `/planner/scenario-builder` 占位路由。
   - 侧边栏新增 Planner 菜单，保持与主系统一致的色板与布局。
2. **Planner 工作区**
   - Initiative 列表：分页、状态/Owner/Tag 筛选、选中高亮。
   - Initiative 详情卡片：名称、状态、日期、标签、描述。
   - 成本包树：调用 `/packages/tree?initiative_id=`，支持搜索过滤与节点选择（联动行项目）。
   - 行项目表：调用 `/line-items`，提供搜索/筛选、分页、inline edit（数量/单价/状态）。
3. **CSV 导入**
   - 触发 `/api/planner/line-items/import`，上传 CSV、指定 initiative。
   - 展示导入 Job 抽屉：轮询 `/line-items/import-jobs/{id}`，显示进度/错误。
4. **Scenario Builder 占位**
   - 页面包含步骤指引、按钮（新建场景/基线对比）和 Modal，先于 Phase 2 占位。
5. **工程与质量**
   - 使用 Zustand 管理选中状态；React Query 负责数据获取。
   - 提供 vitest + Testing Library 配置，至少覆盖 store 工具方法。
   - README + DOC/agents/task_log.md 更新，说明开发步骤、风险与待办。

## 验收
- `npm run dev` 可正常启动，UI 各区域加载后端真实数据。
- Inline edit 成功时自动刷新行列表，导入任务状态实时更新。
- Scenario Builder 页面可正常点击并弹出占位对话框。
- 单元测试与 `npm run build` 通过；task_log 记录结果与风险提示。

---

## Phase 2 – Scenario Ops（2025-12-13）

### 新增能力
- `/planner/scenario-builder` 接入真实接口：`/scenarios/{id}/clone`、`/scenarios/{id}/diff`、`/approvals/*`、`/jobs/{id}`。
- 同一「作业状态抽屉」可查看 CSV 导入、场景克隆、差异分析等任务进度。
- 差异分析支持分页、类型筛选并展示 summary 指标（来源/目标/差异/差异%）。
- 审批卡片提供提交/批准/驳回操作，并可设定 baseline flag。
- 支持手工录入既有场景，便于与后端同步 IDs。

### 操作步骤
1. 在列表中录入或克隆至少两个场景（基线 + 拟比较版本）。
2. 在「差异分析」表单选择来源/对比场景，可选物料类型过滤，点击「获取差异」。
3. 查看 summary 与明细表，如需再次分页可直接使用表格分页控件。
4. 在审批模块选择目标场景并执行「提交」「批准」「驳回」，状态即时刷新。
5. 任何克隆 / diff 行为都会自动打开作业抽屉，可在右侧查看进度、错误记录。

> 截图：`DOC/costing/briefings/img/planner-phase02.png`（待补）

## Phase 3 – Export / Benchmark / Audit（2025-12-13）

### 新功能
1. **场景导出**
   - Scenario 列表卡片与专用表单均可触发 `/scenarios/{id}/export`。
   - 统一进入 Planner Job Drawer，展示导出任务状态。
2. **AI Benchmark 建议**
   - 调用 `/benchmarks/suggest` 输出 Top3/5/10 建议。
   - 支持收藏、重点标记、与场景选择联动。
3. **审计日志**
   - 新增 Drawer，通过 `/audit?target_type=scenario&target_id=...` 查看审批/操作记录。
4. **Bundle 优化**
   - React.lazy 按路由拆包，Scenario Builder 延迟加载。
   - `vite-plugin-imp` 启用 Ant Design 按需样式，减少初始包体。

