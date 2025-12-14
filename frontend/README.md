# Planner Frontend (React 19 + Vite)

Planner 前端为成本规划团队提供 `/planner` 工作区、`/planner/scenario-builder` 场景建模、`/planner/scenarios` 场景资产列表等生产特性。技术栈：React 19、Vite、Ant Design、Zustand、React Query、Vitest。

## 快速开始

```bash
cd frontend
npm install
npm run dev              # http://localhost:4173 （或 http://<服务器IP>:4173）
npm run test -- --run    # Vitest + RTL
npm run build            # 产出 dist/
npm run build:report     # 生成 dist/stats.html (Rollup Visualizer)
npm run deploy:static    # build + 同步 dist/ 至正式静态目录
```

## 静态部署

1. 设置目标目录：`export PLANNER_STATIC_DIR=/srv/nginx/planner`（未设置时默认 `/srv/www/ai-costing-system/planner`）。
2. 执行 `npm run deploy:static`，脚本会自动 `npm run build` 并调用 `scripts/deploy_static.sh` 把 `dist/` 拷贝至目标目录（使用 `rsync --delete`）。
3. 前端不再依赖 `vite preview`；如需验证，使用生产静态目录挂载的域名访问。

## UAT / 生产配置

1. 复制示例：`cp env.production.example .env.production`
2. 根据环境修改变量：

| 变量 | 说明 |
| --- | --- |
| `VITE_PLANNER_API_BASE` | Planner API 网关，如 `https://staging.api.example.com/api/planner` |
| `VITE_PLANNER_SSE_URL` | （可选）Job 状态 SSE，如 `https://staging.api.example.com/api/planner/jobs/sse` |
| `VITE_PLANNER_WS_URL` | （可选）WebSocket 地址，预留给实时审批通知 |
| `VITE_ENABLE_JOB_SSE` | 打开后 `PlannerJobDrawer` 会优先使用 SSE 推送 |
| `VITE_PLANNER_USER_ID` | 调用收藏/Favorite 类接口时使用的 `user_id`（默认 `planner_user`） |

> `.env.production` 仅作为示例，请在 CI/CD 中注入真实变量。

## 主要功能

- `/planner`：initiative 列表 + 成本包树 + 行项目表（内联编辑、分页、CSV 导入、Job Drawer 轮询/SSE）。
- `/planner/scenarios`：支持搜索、按状态/Initiative/Owner/收藏过滤，批量提交审批 & 批量导出（长任务自动弹出 Job Drawer，含 Trace ID/Job ID 一键复制）。
- `/planner/scenario-builder`：基于 API 的场景列表、克隆、差异分析、审批、导出历史时间轴、分页审计日志、AI Benchmark 建议（收藏持久化）。
- `/costing/materials`：物料主数据管理（分页筛选、启用/停用、YiDa 同步日志、CSV/XLSX 导出），为工序/模型配置提供数据底座。
- Observability：所有耗时操作统一 `message.loading` 提示，Drawer/Timeline 提供 Trace ID/Job ID 复制；Audit Drawer 支持 Trace/关键字搜索。

## 性能优化

- 路由级 `React.lazy` + `Suspense`，Planner/Audit Drawer 按需加载。
- `vite-plugin-imp` + 按路径引用 `@ant-design/icons`，减少图标打包体积。
- Rollup `manualChunks` 拆分 react/antd/icons/react-query/zustand/dayjs，Phase 4 目标 main chunk < 400 kB（对比数据记录于 `DOC/agents/task_log.md`）。
- `npm run build:report` 可查看 `dist/stats.html`，建议在每次 UAT 记录主 bundle 前后大小。

## 真实数据联调

1. 填写 `.env.production`，执行 `npm run build && npm run preview`。
2. 重点验证：
   - 场景列表筛选/收藏/批量操作是否能命中 staging 数据。
   - Scenario Builder 左侧导出历史、AI Benchmark 收藏状态是否与后端一致。
   - Job Drawer 是否能在断网/超时后提示“离线/超时”，并保留 Trace ID。
   - 成本核算 → 物料主数据管理页是否能列出真实物料、切换启用状态、触发导出及查看同步日志。
3. 常见网络异常会在页面顶部 `Alert` / 全局 `message.error` 提示。

## 测试

- `npm run test -- --run`：Cover Zustand store、Planner 服务、关键组件行为。
- `npm run build`：保证 TypeScript 检查与产物可用。

如需更多业务操作说明，请阅读 `DOC/costing/manuals/planner_user_guide.md`。*** End Patch
