# AI Costing System

独立的“智能成本核算”项目根目录。推荐结构：

```
ai-costing-system/
  backend/    # FastAPI/Planner 模块（见 backend/README.md）
  frontend/   # React/Vite 页面
  DOC/        # 需求、架构、操作手册
    agents/   # Planner / Executor 说明、task log
```

- 与 `ai-material-system` 并列，但业务逻辑、Git 历史、部署流程完全独立。
- Planner 后端：FastAPI + SQLAlchemy + Alembic，承载 initiatives/packages/line-items
  CRUD、CSV 导入、供应商报价校验、输入假设服务、场景克隆/差异/审批、
  批量导出（真实执行器 HTTP/gRPC 客户端 + 回调签名）、AI Benchmark
  服务代理与收藏、Kafka/RabbitMQ 通知、审计日志与 Prometheus 指标
  `/metrics`。
- 若需要与主系统共享某些依赖，可在 DOC 中记录跨项目接口。

## Ops & Monitoring
- 复制 `.env.sample` 为 `.env`，填写 executor / benchmark / message bus / redis
  等变量，并运行 `python backend/scripts/validate_env.py --env-file .env` 校验。
- 压测脚本：  
  `PLANNER_DATABASE_URL=sqlite:///./planner_loadtest.db PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true \\
   python backend/scripts/run_load_test.py`
  （默认 500 并发导出 + benchmark，输出延迟/失败统计）。
- Prometheus + Grafana：参考 `DOC/costing/manuals/monitoring_setup.md` 并导入
  `monitoring/grafana/planner-integrations.json` 仪表。
- Trace/Audit Runbook：`DOC/costing/manuals/trace_runbook.md` 描述如何根据
  trace_id 联查 audit/job/log。
- Benchmark 降级：若外部服务异常且 `BENCHMARK_FAIL_OPEN=true`（默认），
  后端会自动返回 `source=fallback` 的建议并避免 500；需要完全禁用时可
  将 `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true`。
- Kafka/RabbitMQ 发布具备重试和 `MESSAGE_BUS_PUBLISH_TIMEOUT`，如持续失败会
  打印 `message_bus_fallback` 并落地内存，建议结合监控告警。
- 回滚方案：见 `DOC/costing/handovers/rollback_phase4.md`，通过
  `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true` 立即切回 mock 集成。

## Frontend (feature/costing-frontend)

- 技术栈：React 19 + Vite + Ant Design + Zustand + React Query。
- 进入 `frontend/` 后执行：
  ```
  npm install
  npm run dev        # 启动 http://localhost:4173（已默认监听 0.0.0.0）
  npm run test       # vitest + RTL
  npm run build      # 产出 dist/
  npm run build:report  # 生成 dist/stats.html 打包分析
  ```
- `.env`：`VITE_PLANNER_API_BASE` 默认指向 `http://localhost:8000/api/planner`。如需代理可在 Vite config 中调整。
- Planner UI：
  - `/planner` 展示 initiative 列表/详情、成本包树、行项目表（支持 inline edit + CSV 导入统一作业抽屉）。
  - `/planner/scenarios` 提供场景总览、收藏、筛选、批量提交/导出能力。
  - `/planner/scenario-builder` 接入场景克隆/导出/差异分析/审批流、AI Benchmark 建议（含收藏持久化）、导出历史时间轴及审计 Drawer。
- Bundle 优化：通过 React.lazy 按路由拆包 + `vite-plugin-imp` 按需加载 Ant Design 组件，`npm run build -- --report` 会在 `dist/stats.html` 输出打包报告（当前 Scenario Builder chunk ≈79 kB、Planner Workspace ≈117 kB、主入口 350 kB 内）。
- 任务拆解、验收标准见 `DOC/agents/briefings/frontend_phase01.md`，每日进展同步 `DOC/agents/task_log.md`。







