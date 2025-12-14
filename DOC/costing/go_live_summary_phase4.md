# AI Costing Planner – Phase 4 Go-live Summary

## 1. Scope & Deliverables
- 场景建模：Initiative / Package / Line Item CRUD 与 CSV 导入，统一 PlannerJobDrawer 追踪克隆、导入、导出作业。
- 场景操作：克隆、差异分析、审批（submit/approve/reject）、导出执行系统、AI Benchmark 建议与收藏。
- 可观测性：`/api/planner/audit`（分页+过滤+trace）、Prometheus `/metrics`、消息总线重试&fallback、Trace ID 贯通 Job Drawer / Audit Drawer。
- 文档 & 运维：`go_live_package.md`、`go_live_index.md`、`planner_user_guide.md`、runbook/rollback/monitoring 指南全部更新；静态资源与 CLI 证据归档于 `DOC/costing/images/go-live-20251214/`。

## 2. Validation Evidence
| 流程 | 结果 | 证据 |
| --- | --- | --- |
| 场景克隆 | job `51234a47-4200-4371-a078-441075e0354b` → `SCN-SMOKE-UI-20251214-03` (`ff71964c-dae4-4a02-95d9-ba732d07885d`) | `DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt` 15:40 段 & `go_live_package.md` |
| 审批 | submit trace `257ed63e-b96d-4837-b90e-7c6e1119960b`, approve trace `3f791b92-ee3b-4eb9-a432-c8c4ec0b3a05` | 同上 |
| 导出 | job `4f2ce768-9e54-4204-ae97-8b4d9b78846e`, executor ref `MOCK-ff71964c-dae4-4a02-95d9-ba732d07885d`, audit trace `39eac04b-e461-4cfc-8fa9-66a66d7bc03c` | 同上；Audit Drawer 截图 `DOC/costing/images/go-live-20251214/wechat_2025-12-14_145931_233.png` |
| AI 收藏 | favorite `6f5bcb79-1a17-4b0d-95d2-5fb17820ccf0`, `benchmark_key=materials-unit_cost-ui-smoke-03`, payload 包含 `user_id=planner_user` | `cli-smoke-log-20251214.txt` 15:42 段 & Network 截图 `wechat_2025-12-14_145905_608.png` |
| Audit API | `curl -G http://47.99.89.206:8800/api/planner/audit?page=1&page_size=5` → STATUS 200，最新 5 条含 clone/submit/approve/export/diff | `cli-smoke-log-20251214.txt` 15:36 & 15:45 段 |
| Build & Bundle | `npm run build`、`npm run build:report` 通过；主 React chunk 228 kB gzip | `frontend/dist/stats.html` |
| Backend Tests & Env | `pytest tests/planner -q`、`scripts/validate_env.py`、`scripts/run_load_test.py` 均通过 | 见 `go_live_package.md` 附录 |

## 3. Current System Status（2025-12-14 16:00 CST）
- `planner-api.service`（systemd）已添加 `PYTHONPATH=/home/admin/ai-costing-system/backend`，状态 `active (running)`。
- `/api/planner/audit` 在 8800 端口可用，total=535；Prometheus 指标：`planner_executor_requests_total{status="attempt"}=4`、`{status="success"}=4`，`planner_message_bus_events_total` (SCENARIO_CLONED/SUBMITTED/APPROVED/EXPORTED/DIFF_READY) = 4/4/3/4/1。
- 前端最新构建已部署，Scenario Builder/Audit Drawer 显示真实记录；`DOC/costing/images/go-live-20251214/` 存放全部截图与 CLI log。
- 文档（go_live_package/index、planner_user_guide、runbook、task_log）同步完成，并记录残余风险。

## 4. Residual Risks & Follow-ups
1. **Audit API 对公网放通**：当前仅内网可访问，若需外部用户使用需由 Ops 放开 47.99.89.206:8800/api/planner/audit，并把命令记录在 CLI log。
2. **消息总线 fallback**：尚运行在内存队列模式，需在切换 Kafka/RabbitMQ 后复测 `/metrics` 并观察 lag；若 fallback 告警出现应及时切换 Feature Flag。
3. **QA 复测记录**：等待 QA 根据最新 job/trace ID 更新 `DOC/costing/qa/phase4_regression.md`（尤其是 Audit/API 导出链路）。
4. **前端截图补充**：若有新的 UI 证据（如 diff/导出历史分页等），请继续放入 `DOC/costing/images/go-live-20251214/` 并更新审批包。

## 5. Next Actions
- Planner：依据本文和 `go_live_package.md` 向业务/运维提交上线总结，并在 `DOC/agents/task_log.md` 记录完成情况。
- Ops：决定是否开放公网 Audit API，若执行请更新 CLI log；并持续监控 Prometheus/Kafka 指标。
- QA：按 Phase4 脚本复测并回填 QA 文档；若无新增缺陷，可在 task log 标记 “Phase4 QA – 完成”。
- Backend/Frontend：保持现有分支与远端同步，如需进一步迭代（例如真实执行器、变体规则）可在此基础上开新分支。


