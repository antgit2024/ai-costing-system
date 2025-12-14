---
title: Planner Phase 3.5/4 研发交接注意事项
version: v0.2 (2025-12-13)
owner: Docs Agent
source:
  - DOC/agents/briefings/frontend_phase01.md
  - backend/README.md
---

## 1. Mock 限制与替换计划

| 模块 | 现状 (Mock) | 替换计划 | 注意事项 |
| --- | --- | --- | --- |
| `executor_client.export_scenario` | 仅记录 payload 并返回随机 `reference_id` | Phase 3.5 接入实际成本执行服务（REST），Phase 4 支持回调/状态查询 | 需定义幂等键（scenario_id + version），导出前校验重复推送 |
| `/benchmarks/suggest` | 读取本地种子数据，模拟 AI 建议 | Phase 4 集成 AI Workflow Engine，使用异步任务队列 | 需加入速率限制、结果缓存、失败降级；前端需展示“最后更新”时间 |
| `notification_service` | 仅为占位函数，无真实发送 | Phase 4 对接消息中心（钉钉/邮件） | 结合审批、导出完成、导入失败等事件，支持模板化文案 |

## 2. 真实系统接入步骤

### 2.1 成本执行系统
1. 与执行系统确认 API（预计 `/api/costing/executor/jobs`）。
2. 在 `executor_client` 中新增 token 鉴权与重试逻辑。
3. `planner_import_jobs.result` 中保存执行系统 job id，用于同步状态。
4. 设计 `/scenarios/{id}/export/status` 查询接口（Phase 4）。

### 2.2 AI 服务
1. 依赖 `ai-workflow-engine` 暴露统一接口（Queue + Webhook）。
2. Planner 侧仅存储请求信息与结果摘要，详细报告在 AI 引擎。
3. 需要新增 `ai_benchmark_results` 表（scenario_id, provider, payload, favorites）。

### 2.3 对象存储 & 附件
1. Phase 3.5 计划启用 OSS：新增 `/attachments` 路由 + STS。
2. 前端 Attachment Viewer 通过签名 URL 访问，权限与 initiative 绑定。

## 3. 权限与通知

| 场景 | 权限策略 | 通知策略 |
| --- | --- | --- |
| Initiative / Package / Line Item | 继承现有 SSO 角色（planner/analyst/procurement）+ initiative owner 白名单 | 无 |
| Scenario 操作（克隆/差异/导出） | `planner`、`analyst` 可执行；`approver` 仅阅读 diff | 任务失败/完成后通过通知服务推送给请求人 |
| 审批流 | `approver`、`exec` 角色才能批准；动作写入 `approval_records` | 审批结果实时通知提交人；Phase 4 计划支持抄送 |
| Audit Log | 只读权限，默认所有 planner/QA/审计可访问 | 无 |

> Frontend 需在路由级别读取当前用户角色（SSO token），灰掉不允许的按钮；Backend 通过依赖注入的 `current_user` 校验角色。

## 4. 性能、监控与回滚
- **CSV 导入**：当 `planner_import_jobs.total_rows > 10k` 时启用分批入库；Phase 4 推进 Celery/RQ Worker。
- **差异分析**：>50k 行建议导入临时表后做批处理；考虑启用物化视图缓存最新 diff。
- **Job Drawer/SSE**：优先启用 SSE/WebSocket；若消息服务中断自动回退轮询，同时在 UI 显示告警。
- **Prometheus/Grafana**：关注 `planner_job_duration_seconds`, `scenario_export_fail_total`, `benchmark_latency_seconds`, `planner_messagebus_lag`.
- **回滚策略**：
  1. 关闭 Feature Flag (`PLANNER_FEATURE_EXECUTOR`, `PLANNER_FEATURE_BENCHMARK`, `PLANNER_FEATURE_SCENARIO_LIST` 等)。
  2. 回滚 Alembic 迁移（如 favorites/callback 表）。
  3. 清理未消费的 Kafka/RabbitMQ 消息或切换到备用通道。
  4. 恢复数据库/配置备份并重启服务。

## 5. Phase 4 运行手册

| 项目 | 运营指南 | 监控 / 回滚 | Known Issues |
| --- | --- | --- | --- |
| **Executor 集成** | 真实导出会调用外部 API，务必传入 trace_id 与幂等键 | 监控执行耗时与失败率；若外部异常，切换 feature flag → mock | 当回调延迟>30s 时 Job Drawer 状态不同步；建议手工刷新或查看 export history |
| **Scenario 列表/收藏** | `/planner/scenarios` 提供批量提交/导出与收藏 | 若列表超时，UI 会提示「离线」并缓存最后成功数据 | 收藏状态可能因消息总线延迟不同步；可手动刷新或联系后端排查 |
| **AI Benchmark Provider** | 使用真实 provider + 缓存；收藏可跨页面共享 | 监控 `benchmark_latency_seconds` 与缓存命中率；失败时 fallback 到最近缓存 | Provider 返回字段变化会导致 UI 展示异常，需在 Feature Flag 层控制 |
| **消息总线（Kafka/RabbitMQ）** | 发布 `SCENARIO_APPROVED/EXPORTED/DIFF_READY` 事件 | 关注 Lag 指标与死信队列；必要时切换到备用 broker | 若消费者异常，事件会堆积，需手动重放；请记录 trace_id 便于定位 |
| **通知服务** | Phase 4 启用钉钉/邮件模板 | 失败时写入 `notification_fail_total`; 可配置重试 | 若通知模板变更需同步文档，否则会产生错漏 |

### 排查步骤
1. **确认 Trace**：所有 UI 都显示 trace_id/job_id，复制后查 `audit_logs` 与 `planner_import_jobs`。
2. **查看日志**：在 backend 中 grep trace_id，确认 executor / benchmark / message bus 的往返。
3. **核对消息**：使用消费者脚本读取 `planner.events`，确认事件是否发布/消费。
4. **执行回滚**：若问题在外部系统，先切换 feature flag → mock，恢复后再逐步打开。

## 6. 交接清单
1. **代码**：Backend/Frontend Phase 3.5 分支合并，Feature Flag 默认 `mock`，上线前手动切换。
2. **文档**：更新 `DOC/costing/architecture.md`、`DOC/costing/manuals/`、`DOC/costing/qa/phase4_regression.md`。
3. **数据**：维护 `sample_data` 和 staging 回归脚本，确保与生产 schema 同步。
4. **运维**：Prometheus/Grafana 仪表、Kafka/RabbitMQ 监控、OSS/回调白名单配置完成。

> 如需扩展 Phase 4（项目管理、批量任务、实时通知细化），建议在 `feature/costing-docs/phase4` 目录撰写 RFC 并同步任务分解。

## 7. QA 结果纪要（2025-12-13）
- 完整执行 CSV → 克隆 → 差异 → 审批 → 导出 → AI Benchmark 收藏 → 消息事件链路，参考 `DOC/costing/qa/phase4_regression.md`。
- **通过**：CSV 导入、克隆、导出、批量提交、Kafka 事件校验。
- **告警**：审批通知延迟约 3 分钟（Trace `TRACE-APPROVE-01`），需在通知服务增加延迟监控。
- **失败**：AI Benchmark Provider 返回 500（Trace `TRACE-AI-FAIL-01`），UI 依赖缓存；上线前需准备降级策略或开关。
- Ops需根据结果更新监控：增加通知延迟告警、Benchmark 错误率指标，并在故障时切换回 mock provider。

## 8. 上线完成说明
- **上线窗口**：2025-12-14 00:00–02:00 CST，按 go_live_index 中审批计划执行。
- **部署动作**：切换 Feature Flag 为 `real` → 滚动发布 backend/frontend → 运行 smoke（CSV 导入、克隆、导出、AI 收藏、场景列表、导出历史、Job/Audit Drawer）→ 校验 Prometheus/Kafka/Sentry 指标。
- **Backend 回执**：00:05–00:35 完成滚动重启与 smoke（Trace `TRACE-BE-SMOKE-01`），Prometheus `planner_job_duration_seconds`、Kafka Lag 正常。
- **Frontend 回执**：00:20–00:45 发布新版 bundle（<400 kB），Smoke 覆盖场景列表/导出历史/AI 收藏/Job Drawer；Console/Sentry 无新增错误。
- **结果**：全部 smoke 测试通过，30 分钟内监控无异常；AI fallback 告警、通知延迟监控均保持绿色。
- **回滚联系人**：Zhang Wei（架构）、Liu Fang（DevOps）、Chen Qiao（QA）。触发条件参考章节 4 回滚策略。

