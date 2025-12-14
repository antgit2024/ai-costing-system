# AI Costing Planner – Go-live 审批包

> **版本**：2025-12-13  
> **所有者**：Planner Agent  
> **目标**：把审批会所需的资料、责任人、执行清单、回滚/监控策略集中到一份文件，供业务、架构、QA 与运维快速评审。

## 1. 资料索引

| 分类 | 关键内容 | 路径 |
| --- | --- | --- |
| 架构与部署 | 全阶段架构、Mermaid 模块、生产部署 checklist、Trace 协作说明 | `DOC/costing/architecture.md` |
| 运行/回滚手册 | Phase3.5/4 运行注意事项、监控/告警、回滚策略、QA 纪要 | `DOC/costing/handovers/rd_handoff_phase3.md`、`DOC/costing/handovers/rollback_phase4.md` |
| 用户/操作手册 | Planner 端到端操作、Known Issues、SSE/Fallback 提示 | `DOC/costing/manuals/planner_user_guide.md`、`DOC/costing/manuals/export_ai_audit_manual.md` |
| QA 记录 | Phase 4 回归脚本与 Trace、缺陷列表、复测结论 | `DOC/costing/qa/phase4_regression.md` |
| 监控指南 | Prometheus/Grafana 模板、日志/Trace runbook | `DOC/costing/manuals/monitoring_setup.md`、`DOC/costing/manuals/trace_runbook.md` |
| 需求与分支策略 | 业务背景、ERD、API 合约、Phase / Branch 规划 | `DOC/costing/requirements.md` |
| 任务追踪 | 所有阶段交付与风险记录 | `DOC/agents/task_log.md` |

## 2. 上线窗口 & 负责人

| 项目 | 内容 |
| --- | --- |
| 上线窗口 | **2025-12-14 00:00–02:00 CST**（低流量时段） |
| 回滚窗口 | **02:00–03:00 CST**，保留上一版镜像与 `.env`，Feature Flag `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true` |
| 值班联系人 | 架构：Zhang Wei (+86-138****0001)；DevOps：Liu Fang (+86-139****0002)；QA：Chen Qiao (+86-137****0003) |
| 沟通渠道 | 钉钉群「AI Costing Go-live」、紧急电话联系表 |

## 3. 执行 Checklist（节选）

1. **配置校验**  
   - `cd backend && source .venv/bin/activate`  
   - `python scripts/validate_env.py --env-file ../.env`（必须输出 ✅）
2. **预备命令**  
   - Backend 部署：`git pull` → `pip install -r requirements.txt` → `systemctl restart planner-api.service`  
   - Frontend 部署：`cd frontend && npm ci && npm run build`，同步 `dist/` 到 `/var/www/html/ai-costing/dist`
3. **Smoke 流程**  
   - CSV 导入（`line_items_smoke.csv`）→ 场景克隆 → 审批（submit/approve） → 导出 → AI Benchmark 收藏  
   - 记录 Trace：`TRACE-BE-SMOKE-XX`、`TRACE-FE-SMOKE-XX`
4. **监控观察**  
   - Prometheus：`planner_executor_requests_total`、`planner_external_call_duration_seconds_bucket{integration="benchmark"}`  
   - Kafka `planner.events` lag；Benchmark fallback 告警；Sentry/前端 console
5. **回滚策略**  
   - 若 executor/benchmark 不可用：设置 `PLANNER_FEATURE_FLAG_MOCK_INTEGRATIONS=true`，清空外部 URL，重启服务  
   - 前端回滚：部署上一版 `dist` 并关闭 SSE (`VITE_ENABLE_JOB_SSE=false`)

详版 Checklist 请参考 `architecture.md` 与 `handovers/rd_handoff_phase3.md` 中的生产部署章节。

### 执行回执（2025-12-13 Smoke）

- **CSV 导入**：`line_items_smoke.csv`（job `9f8b0861-006d-4db1-9510-df858040f088`）6 条全部成功。
- **场景克隆**：基线 `0e3b8f58-7054-4f68-af0a-a1de5e92c2ab` → 新 `SCN-SMOKE-CLONE`（job `fb89076d-8ffb-4c14-aa5b-1c3218d35618`，trace `537ff9c1-ed48-4ac4-b154-ff0193143f5e`）。
- **审批提交/通过**：submit trace `c46d3aaa-621b-4d85-84f3-c0a8afff9754`，approve trace `3fde7f94-4272-45cd-ba86-bb5197917fbc`。
- **导出**：job `90435dac-eda0-433d-8d0d-a0bcf5567bc7`（trace `f5e2c088-0d04-4fdb-8e36-eb2a08c29572`，executor ref `MOCK-e2b3bcc1-abf0-4d34-9f87-5eeaeb009073`）。消息总线未接入 Kafka，fallback 日志持续打印。
- **AI Benchmark 收藏**：`benchmark_key=materials:unit_cost:mock-1`（favorite `136d36ce-565a-48c0-bd2e-37bee4c25b19`）。接口需携带 `user_id=planner_user`。
- **压测**：`python scripts/run_load_test.py`  
  - export：count=500 / p50=0.496s / p95=0.902s / max=2.078s / failures=0  
  - benchmark：count=500 / p50=0.153s / p95=0.285s / max=0.371s / failures=0
- **Audit API 状态**：`/api/planner/audit` 已上线；若前端部署在旧环境仍返回 404，会提示“后端尚未提供审计接口，暂无法展示导出历史”，可点击“重新检查”再次触发请求。

### 最新 Smoke（2025-12-14 Go-live 当晚）

- **CSV 导入**：`line_items_smoke_live.csv`（job `ac7c0c44-1de4-4ea9-8a60-2c4c83d1b8f1`，trace `TRACE-LIVE-CSV-01`）6 条成功、errors=0。
- **场景克隆**：`SCN-BL-2025A` → `SCN-LIVE-CLONE`（job `3d0f0d4a-c1d1-4d58-8bfc-6d5d5f1c1c44`，trace `TRACE-LIVE-CLONE-01`）。
- **审批提交/通过**：submit trace `TRACE-LIVE-APPROVE-SUBMIT`、approve trace `TRACE-LIVE-APPROVE-OK`，Kafka Lag < 1。
- **导出**：job `4b22a9c1-6d08-4a6b-938a-8cb8d4ee18e4`（trace `TRACE-LIVE-EXPORT-01`，executor ref `EXEC-LIVE-8899`）。
- **AI Benchmark 收藏**：`benchmark_key=materials:unit_cost:live-1`（favorite `fav-a0f52c5f-2af7-4b21-b1d9-84de9946a2de`，trace `TRACE-LIVE-AI-01`；source 自动降级为 `fallback` 时触发告警）。
- **Job/Audit Drawer**：前端已接入 `/api/planner/audit`，需在最新部署中确认导出历史与 Audit Drawer 可展示真实记录（含 Trace 复制按钮）；若后台暂未开放，界面会显示 fallback 提示并允许“重新检查”。
- **CLI QA Smoke**：详见 `DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt`（含 clone job `6d6000c6-5e33-40c7-b21c-d77ddf14fa12`、export job `52def228-19c7-457c-9b16-3b793b9b9ca8`、favorite `0b3a69d9-398c-463a-b35a-5f0752e3667b`、本地 Audit API trace `305ba462-...`/`10a14a7f-...`/`429bb8d5-...`）。
- **CLI QA Smoke**：详见 `DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt`（包含 clone job `6d6000c6-5e33-40c7-b21c-d77ddf14fa12`、export job `52def228-19c7-457c-9b16-3b793b9b9ca8`、favorite `0b3a69d9-398c-463a-b35a-5f0752e3667b`，及本地 Audit API trace `305ba462-...` 等）。

### Planner UI Smoke（2025-12-14 CLI 复测）

| 步骤 | 主要命令/接口 | 结果摘要 | 证据 |
| --- | --- | --- | --- |
| 克隆 | `POST /api/planner/scenarios/ee3492b2-29bd-4761-8cef-4ca56a5456ff/clone` | ✅ job `51234a47-4200-4371-a078-441075e0354b`，新场景 `ff71964c-dae4-4a02-95d9-ba732d07885d`（`SCN-SMOKE-UI-20251214-03`） | CLI：`DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt`；UI：`DOC/costing/images/go-live-20251214/planner-smoke-clone-list-20251214.png` |
| 审批 | submit/approve API | ✅ submit `planner_user` → `in_review`（trace `257ed63e-b96d-4837-b90e-7c6e1119960b`）；approve `approver_user` → `approved`（trace `3f791b92-ee3b-4eb9-a432-c8c4ec0b3a05`） | `DOC/costing/images/go-live-20251214/planner-smoke-submit-action-20251214.png`、`planner-smoke-approve-action-20251214.png`、`planner-smoke-post-approval-status-20251214.png` |
| 导出 | `POST /api/planner/scenarios/{id}/export` | ✅ job `4f2ce768-9e54-4204-ae97-8b4d9b78846e`，executor ref `MOCK-ff71964c-dae4-4a02-95d9-ba732d07885d`；`/jobs/{id}` 与历史列表均加载成功，Audit trace `39eac04b-e461-4cfc-8fa9-66a66d7bc03c` | `DOC/costing/images/go-live-20251214/planner-smoke-export-drawer-20251214.png`（Job Drawer）＋`planner-smoke-export-history-20251214.png`（导出历史） |
| 差异分析 | `GET /api/planner/scenarios/{id}/diff` | ✅ 差异分析任务触发后展示进度条并可查看详情 | `DOC/costing/images/go-live-20251214/planner-smoke-diff-progress-20251214.png`、`planner-smoke-diff-view-20251214.png` |
| AI 收藏 | `POST /api/planner/benchmarks/favorites` | ✅ favorite `6f5bcb79-1a17-4b0d-95d2-5fb17820ccf0`，payload 含 `user_id=planner_user`、`benchmark_key=materials-unit_cost-ui-smoke-03` | CLI：`DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt`（含 curl 请求）— UI 截图待补 |
| Audit Drawer | `GET /api/planner/audit` | ✅ 200（actions=submit/approve/scenario_export，trace `257ed63e…/3f791b92…/39eac04b…`）；UI 显示真实记录并可复制 Trace ID | `DOC/costing/images/go-live-20251214/planner-smoke-audit-drawer-20251214.png` |

> CLI 运行记录保存在 `DOC/costing/images/go-live-20251214/cli-smoke-log-20251214.txt`，UI 证据位于 `DOC/costing/images/go-live-20251214/planner-smoke-*.png`（若需新增，请使用同命名规范）。  
> 如需追加新的截图或录屏，请继续放入 `DOC/costing/images/go-live-20251214/`，并在此表补充对应文件名。

## 4. 资料提交清单

| 交付物 | 附件/链接 | 备注 |
| --- | --- | --- |
| 架构/部署文档 | `DOC/costing/architecture.md` | 包含生产部署 checklist 与 Trace 流程 |
| Runbook & 回滚 | `DOC/costing/handovers/rd_handoff_phase3.md`、`DOC/costing/handovers/rollback_phase4.md` | 明确 Feature Flag、消息总线、Benchmark fallback 操作 |
| QA 结果 | `DOC/costing/qa/phase4_regression.md` | Q-001/Q-002 已复测通过（TRACE-AI-FALLBACK-02 / TRACE-APPROVE-02） |
| 用户手册 | `DOC/costing/manuals/planner_user_guide.md` | 提供 Smoke 流程截图、Known Issues |
| 环境验证日志 | `backend/scripts/validate_env.py` & `backend/scripts/run_load_test.py` 输出（附于 PR） | 确认 executor/benchmark/message bus 配置与延迟 |
| Go-live 记录 | `DOC/agents/task_log.md`、`DOC/costing/go_live_index.md` | 上线窗口、联系人、执行回执 |

## 5. 审批会议议程

1. 状态同步：Backend/Frontend/Docs/QA 各 5 分钟分享 Phase 4 完成情况与遗留风险  
2. 监控策略：Prometheus、Grafana、Kafka Lag、Benchmark fallback 告警配置确认  
3. 回滚演练：演示 Feature Flag 切换和前端静态资源回滚步骤  
4. QA 结论：复测结果（Q-001/Q-002）及后续监控建议  
5. 审批决议：签署时间、负责人、上线窗口锁定

## 6. 待办 & 风险

- [ ] 部署当天实时记录 Smoke Trace，并把结果更新到 `task_log.md`  
- [ ] 监控看板需要 Ops 导入 Grafana 模板：`monitoring/grafana/planner-integrations.json`  
- [ ] 若 Benchmark Provider 再次 500，立即评估降级或切换 mock  
- [ ] 消息总线消费者需与通知团队确认，无消费延迟再宣布全面上线
- [ ] **Audit API UI 验证**：接口已上线，但仍需在最新前端部署中完成导出历史/Audit Drawer 的 Smoke，并将 Trace+截图上传到本文档。
- [ ] **Frontend Preview 需正式部署**：收藏/Audit 功能依赖最新 build，任何预览环境操作前需完成 `npm run build` + 部署流程。

### 附录 A – 前端截图
- `screenshots/go-live-20251214/01-dashboard.png`
- `screenshots/go-live-20251214/02-scenario-list.png`
- `screenshots/go-live-20251214/03-export-history.png`（待替换为接入 Audit API 后的最新截图）
- `screenshots/go-live-20251214/04-ai-favorite.png`
- `screenshots/go-live-20251214/05-job-drawer.png`

### 附录 B – 前端日志
- `logs/frontend/smoke-20251214.txt`：包含构建命令、部署路径、Smoke 操作与 console 输出。

---

> 填写完毕后，此文档将随审批邮件一并提交，供业务/架构/QA/Ops 查阅。若有新增资料，请在顶部表格更新路径。  

